FROM python:3.11.9-slim-bookworm

# Set working directory
WORKDIR /app
COPY . .

# Optional: make sure folder exists in dev/local builds
RUN mkdir -p .job_db

# Copy only the API requirements first to leverage Docker caching
COPY requirements-server.txt .

# Install only server-side libraries (keeps image small)
RUN pip install --no-cache-dir -r requirements-server.txt

# Update OS packages to fix known vulnerabilities
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Now copy the rest of the project
COPY . .

# Run the FastAPI server
CMD ["uvicorn", "modules.core.job_api_server:app", "--host", "0.0.0.0", "--port", "8080"]
