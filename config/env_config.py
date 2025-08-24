import os
from pathlib import Path
from dotenv import load_dotenv
from modules.gmail_reader import OTPFetcher

load_dotenv()

# 🔗 Project root directory
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 📂 Directory paths
CACHE_DIR = PROJECT_ROOT / os.getenv("CACHE_DIR", ".cache")
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", ".chroma_db")
NLTK_DATA_DIR = PROJECT_ROOT / os.getenv("NLTK_DATA_DIR", ".cache/nltk_data")
LOG_DIR = PROJECT_ROOT / os.getenv("LOG_DIR", ".logs")
JOB_DB_DIR = os.getenv("JOB_DB_DIR", ".job_db")

# 📄 File paths
DRIVER_PATH = PROJECT_ROOT / os.getenv("DRIVER_PATH", "config/chromedriver-win64/chromedriver.exe")
USER_JSON_FILE = PROJECT_ROOT / os.getenv("USER_JSON_FILE", "config/user_data.json")
GMAIL_CREDENTIALS_FILE = PROJECT_ROOT / os.getenv("GMAIL_CREDENTIALS_FILE", ".credentials/client_secret.json")
GMAIL_TOKEN_FILE = PROJECT_ROOT / os.getenv("GMAIL_TOKEN_FILE", ".credentials/token.json")
JOB_QUEUE_FILE = PROJECT_ROOT / os.getenv("JOB_QUEUE_FILE", ".job_db/job_queue.json")
JOB_RESULTS_FILE = PROJECT_ROOT / os.getenv("JOB_RESULTS_FILE", ".job_db/job_results.json")

# 🔐 Remove stale lock file if left by previous run
token_lock_file = GMAIL_TOKEN_FILE.with_suffix('.json.lock')
if token_lock_file.exists():
    token_lock_file.unlink()

# 📄 File names
HASH_FILE = os.getenv("HASH_FILE", os.path.join(CHROMA_DB_DIR, "hash.txt"))

# Job Database
FLY_VOLUME_NAME = os.getenv("FLY_VOLUME_NAME")
FLY_REGION = os.getenv("FLY_REGION")
IMAGE_NAME = os.getenv("IMAGE_NAME", "jobpilot")
TAG = os.getenv("TAG", "latest")
PORT = int(os.getenv("PORT", 8080))
JOB_DB = PROJECT_ROOT / os.getenv("JOB_DB", ".job_db/job_store.db")
REMOTE_JOB_API_URL = os.getenv("REMOTE_JOB_API_URL", "http://127.0.0.1:8000")

# 🔤 Config values
BROWSER_NAME = os.getenv("BROWSER_NAME")
EMBED_MODEL = os.getenv("EMBED_MODEL")
EMBED_COLLECTION_NAME = os.getenv("EMBED_COLLECTION_NAME", "jobpilot_user_context")
LLM_MODEL = os.getenv("LLM_MODEL")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")


### OLD
# LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
# LOG_DIR = os.getenv("LOG_DIR", ".logs")
# DRIVER_PATH = os.getenv("DRIVER_PATH")
# GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE")
# GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE")


# ✅ Assertions for critical configs — fail fast
assert LOG_LEVEL, "❌ LOG_LEVEL not set in .env"
assert DRIVER_PATH, "❌ DRIVER_PATH not set in .env"
assert BROWSER_NAME in ["Brave", "Chrome"], f"❌ BROWSER_NAME must be 'Brave' or 'Chrome', got: {BROWSER_NAME}"
assert os.path.isfile(USER_JSON_FILE), f"User Data directory not found: {USER_JSON_FILE}"
assert EMBED_MODEL, "❌ EMBED_MODEL not set in .env"
assert EMBED_COLLECTION_NAME, "❌ EMBED_COLLECTION_NAME not set in .env"
assert HASH_FILE.endswith("hash.txt"), f"Invalid hash file name: {HASH_FILE}"
assert LLM_MODEL, "❌ LLM_MODEL not set in .env"
assert os.path.isfile(GMAIL_CREDENTIALS_FILE), "❌ GMAIL_CREDENTIALS_FILE not found."


# 📁 Ensure required directories exist
if not os.path.isdir(CHROMA_DB_DIR):
    print(f"👀  Chroma DB directory not found")
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    print(f"📂  Chroma DB directory created at {CHROMA_DB_DIR}")

if not os.path.isdir(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

if not os.path.isdir(JOB_DB_DIR):
    os.makedirs(JOB_DB_DIR, exist_ok=True)

# 📄 Ensure required files exist
for file_path in [JOB_QUEUE_FILE, JOB_RESULTS_FILE]:
    if not file_path.exists():
        # print(f"📄  Creating missing file: {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        file_path.touch()

# 📥 Gmail Fetcher
otp_fetcher = OTPFetcher(
        credentials_file=GMAIL_CREDENTIALS_FILE,
        token_file=GMAIL_TOKEN_FILE,
        enable_logging=True
    )