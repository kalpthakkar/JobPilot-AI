# modules/core/job_api_server.py
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi import Path as FastAPIPath
from urllib.parse import unquote
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import List
import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_DB_DIR = os.getenv("JOB_DB_DIR", ".job_db")    # Fly.io volume path
if not os.path.isdir(JOB_DB_DIR):
    os.makedirs(JOB_DB_DIR, exist_ok=True)

JOB_DB = PROJECT_ROOT / os.getenv("JOB_DB", ".job_db/job_store.db")
DB_PATH = JOB_DB

# ✅ Lifespan context manager for FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ Job DB initialized on startup")
    yield
    print("🔻 FastAPI is shutting down...")

app = FastAPI(lifespan=lifespan)

# ✅ CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Initialize DB schema
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS job_queue (
            url TEXT PRIMARY KEY,
            status TEXT CHECK(status IN ('new', 'active', 'success', 'failed')) NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ✅ Pydantic Schemas
class JobUpdate(BaseModel):
    url: str
    status: str

class JobList(BaseModel):
    urls: List[str]

class JobInsert(BaseModel):
    urls: List[str]
    status: str = "new"
    update_if_exists: bool = Query(False, description="If True, update existing jobs; if False, skip existing jobs")

# === API Routes ===

@app.get("/next-job")
def get_next_job():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url FROM job_queue WHERE status='new' LIMIT 1")
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No new jobs available")
    url = row[0]
    c.execute("UPDATE job_queue SET status='active', updated_at=CURRENT_TIMESTAMP WHERE url=?", (url,))
    conn.commit()
    conn.close()
    return {"url": url}

@app.post("/refresh-job")
def refresh_job(update: JobUpdate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if job already exists
    c.execute("SELECT 1 FROM job_queue WHERE url = ?", (update.url,))
    exists = c.fetchone()
    if exists:
        c.execute(
            "UPDATE job_queue SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE url = ?",
            (update.status, update.url),
        )
    else:
        c.execute(
            "INSERT INTO job_queue (url, status) VALUES (?, ?)",
            (update.url, update.status),
        )
    conn.commit()
    conn.close()
    return {"message": f"Job {update.url} set to status {update.status}"}

@app.post("/job/update")
def update_job(update: JobUpdate = Body(...)):
    url = update.url
    status = update.status
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE job_queue SET status=?, updated_at=CURRENT_TIMESTAMP WHERE url=?", (status, url))
    if c.rowcount == 0:
        c.execute("INSERT INTO job_queue (url, status) VALUES (?, ?)", (url, status))
    conn.commit()
    conn.close()
    return {"message": f"Job status updated to {status} for url {url}"}

@app.get("/all-jobs")
def list_jobs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, status FROM job_queue ORDER BY created_at DESC")
    jobs = [{"url": url, "status": status} for url, status in c.fetchall()]
    conn.close()
    return {"jobs": jobs}

# ✅ Dev-only: Bulk insert test jobs
@app.post("/load-jobs")
def load_jobs(batch: JobList):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    added, skipped = 0, 0
    for url in batch.urls:
        try:
            c.execute("INSERT OR IGNORE INTO job_queue (url, status) VALUES (?, 'new')", (url,))
            if c.rowcount > 0:
                added += 1
            else:
                skipped += 1
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))
    conn.commit()
    conn.close()
    return {"added": added, "skipped": skipped, "total": len(batch.urls)}

@app.post("/admin/reset")
def reset_jobs(reset_type: str = "truncate"):
    """
    reset_type options:
    - 'truncate': deletes all jobs
    - 'new': sets all statuses to 'new'
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if reset_type == "truncate":
        c.execute("DELETE FROM job_queue")
    elif reset_type == "new":
        c.execute("UPDATE job_queue SET status='new', updated_at=CURRENT_TIMESTAMP")
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid reset_type. Use 'truncate' or 'new'")
    conn.commit()
    conn.close()
    return {"message": f"Job table reset with method: {reset_type}"}

@app.post("/add-jobs")
def add_jobs(job_data: JobInsert):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    added = 0
    skipped = 0

    try:
        for url in job_data.urls:
            if job_data.update_if_exists:
                # Insert or replace (overwrite existing job)
                c.execute(
                    "INSERT OR REPLACE INTO job_queue (url, status) VALUES (?, ?)",
                    (url, job_data.status)
                )
                added += 1
            else:
                # Insert only if not exists
                c.execute(
                    "INSERT INTO job_queue (url, status) "
                    "SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM job_queue WHERE url=?)",
                    (url, job_data.status, url)
                )
                if c.rowcount == 1:
                    added += 1
                else:
                    skipped += 1
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

    return {
        "message": (
            f"{added} job(s) added/updated, {skipped} skipped because they already exist "
            f"(when skipping was chosen)."
        ),
        "update_if_exists": job_data.update_if_exists,
    }

@app.get("/jobs-by-status/{status}")
def get_jobs_by_status(status: str):
    valid_statuses = {"new", "active", "success", "failed"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status filter.")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url FROM job_queue WHERE status=?", (status,))
    data = c.fetchall()
    conn.close()
    return {"urls": [url for (url,) in data]}

# @app.post("/refresh-job")
# def refresh_job(update: JobUpdate):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("SELECT 1 FROM job_queue WHERE url=?", (update.url,))
#     exists = c.fetchone()
#     if exists:
#         c.execute("UPDATE job_queue SET status=? WHERE url=?", (update.status, update.url))
#     else:
#         c.execute("INSERT INTO job_queue (url, status) VALUES (?, ?)", (update.url, update.status))
#     conn.commit()
#     conn.close()
#     return {"message": f"Job {update.url} set to status {update.status}"}



