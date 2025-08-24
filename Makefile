# Makefile for JobPilot AI: Combined API Server & Job Runner Docker Workflow

# ==== Load Environment ====
include .env
export $(shell sed 's/=.*//' .env)

# ==== Configuration ====
IMAGE_NAME = jobpilot
_TAG = $(TAG)
_DO_PORT = $(PORT)
_FLY_VOLUME_NAME = $(FLY_VOLUME_NAME)
_FLY_REGION = $(FLY_REGION)
UVICORN_RELOAD ?= --reload
_REMOTE_JOB_API_URL ?= $(REMOTE_JOB_API_URL)
_FASTAPI_APP_NAME ?= $(FASTAPI_APP_NAME)
_FASTAPI_SERVER_PATH ?= $(FASTAPI_SERVER_PATH)

# ==== Targets ====
.PHONY: help venv-shell docker-build docker-run docker-shell deploy clean logs docker-build-clean prune prune-all clean-pycache clean-logs clean-all create-volume test_env serve-api jobs add-job add-jobs jobs-status refresh-job

help:
	@echo "Usage:"
	@echo "  make venv-shell       Activate virtual environment"
	@echo "  make docker-build     Build the Docker image"
	@echo "  make docker-run       Run the Docker image locally"
	@echo "  make docker-shell     Open shell in Docker container"
	@echo "  make deploy           Deploy project to Fly.io"
	@echo "  make clean            Remove Docker image"
	@echo "  make logs             Tail logs from Fly.io deployment"
	@echo "  make docker-build-clean Build image and prune unused Docker resources"
	@echo "  make prune            Clean up unused Docker resources (safe)"
	@echo "  make prune-all        Aggressive Docker cleanup (includes volumes, old images)"
	@echo "  make clean-pycache    Remove Python __pycache__ directories"
	@echo "  make clean-logs       Remove local log files"
	@echo "  make clean-all        Clean image, pycache, logs, and prune system"
	@echo "  make create-volume    Create Fly.io volume using .env variables"
	@echo "  make test_env         Show current environment variables"
	@echo "  make serve-api        Run FastAPI server with uvicorn"
	@echo "  make jobs             View all jobs from API"
	@echo "  make add-job          Add a single job (status=new) via API"
	@echo "  make add-jobs         Add multiple jobs (comma-separated URLs) via API"
	@echo "  make jobs-status      View jobs filtered by status via API"
	@echo "  make refresh-job      Refresh or add job with new status via API"

venv-shell:
ifeq ($(OS),Windows_NT)
	@start powershell -NoExit -Command ". .\\venv_jobpilot\\Scripts\\Activate.ps1"
else
	@source ./venv_jobpilot/Scripts/activate
	@exec bash
endif

docker-build:
	docker build -t $(IMAGE_NAME):$(_TAG) -f $(DOCKERFILE) .

docker-run:
	docker run --rm -p $(_DO_PORT):8080 --env-file .env $(IMAGE_NAME):$(_TAG)

docker-shell:
	docker run -it --env-file .env --entrypoint /bin/bash $(IMAGE_NAME):$(_TAG)

deploy:
	fly deploy --remote-only

logs:
	fly logs

clean:
	docker rmi $(IMAGE_NAME):$(_TAG) || true

docker-build-clean: docker-build prune

prune:
	docker system prune -f

prune-all:
	docker system prune -a -f --volumes

clean-pycache:
	find . -type d -name "__pycache__" -exec rm -rf {} +

clean-logs:
	rm -rf .logs/*.log || true

clean-all: clean clean-pycache clean-logs prune

create-volume:
	fly volumes create $(_FLY_VOLUME_NAME) -s 1 -r $(_FLY_REGION)

test_env:
	@echo "================ .env CONFIG ================"
	cat .env
	@echo "============================================"

# === API Interaction Utilities ===

serve-api:
	uvicorn $(strip $(_FASTAPI_SERVER_PATH)):$(strip $(_FASTAPI_APP_NAME)) $(UVICORN_RELOAD) --port $(_DO_PORT)

# View all jobs
jobs:
	curl -s $(_REMOTE_JOB_API_URL)/all-jobs | jq

# Add a single job (status = new)
add-job:
	curl -X POST $(_REMOTE_JOB_API_URL)/add-jobs \
		-H "Content-Type: application/json" \
		-d '{"urls": ["https://example.com"], "status": "new"}' | jq

# Add multiple jobs (use comma-separated list)
add-jobs:
	@echo "Enter comma-separated list of URLs:"; \
	read urls; \
	json=$$(echo $$urls | awk -F, '{printf "[\"%s\"", $$1; for (i=2; i<=NF; i++) printf ", \"%s\"", $$i; print "]"}'); \
	echo "Update existing jobs if they exist? (true/false):"; \
	read update_flag; \
	curl -X POST $(_REMOTE_JOB_API_URL)/add-jobs \
		-H "Content-Type: application/json" \
		-d "{\"urls\": $$json, \"status\": \"new\", \"update_if_exists\": $$update_flag}" | jq

# Filter jobs by status
jobs-status:
	@echo "Enter status (new, active, success, failed):"; \
	read status; \
	curl -s $(_REMOTE_JOB_API_URL)/jobs-by-status/$$status | jq

# Refresh job (reset status or add if doesn't exist)
refresh-job:
	@echo "Enter job URL:"; read url; \
	echo "Enter new status (new, active, success, failed):"; read status; \
	curl -X POST $(_REMOTE_JOB_API_URL)/refresh-job \
		-H "Content-Type: application/json" \
		-d "{\"url\": \"$$url\", \"status\": \"$$status\"}" | jq
