#!/usr/bin/env bash
# scaffold_repo.sh
# Creates the complete Contract Intelligence monorepo skeleton in the CURRENT
# directory: two independently-deployable services, placeholder modules, per-
# service pyproject.toml (uv), .env.example, .gitignore, and a README.
# Run this from the folder where you want the project to live. Idempotent-ish:
# it will not overwrite files that already exist.
set -euo pipefail

ROOT="contract-intel"
info() { printf "\033[0;34m==>\033[0m %s\n" "$1"; }

if [ -d "$ROOT" ]; then
  echo "ERROR: '$ROOT' already exists here. Move/rename it or run elsewhere."
  exit 1
fi

info "Creating directory tree"
mkdir -p "$ROOT"/{django_app/config,django_app/accounts,django_app/documents,django_app/analytics}
mkdir -p "$ROOT"/ai_service/app/{agent,tools,rag,sinks,schemas}
mkdir -p "$ROOT"/{infra,scripts}

cd "$ROOT"

# --- python package markers -------------------------------------------------
info "Adding __init__.py markers"
for d in django_app/config django_app/accounts django_app/documents django_app/analytics \
         ai_service/app ai_service/app/agent ai_service/app/tools ai_service/app/rag \
         ai_service/app/sinks ai_service/app/schemas; do
  touch "$d/__init__.py"
done

# --- django pyproject -------------------------------------------------------
info "Writing django_app/pyproject.toml"
cat > django_app/pyproject.toml <<'EOF'
[project]
name = "contract-intel-web"
version = "0.1.0"
description = "Django product layer: auth, documents, jobs, ops admin"
requires-python = ">=3.12"
dependencies = [
    "django>=5.1",
    "dj-database-url>=2.2",
    "psycopg[binary]>=3.2",
    "gunicorn>=23.0",
    "python-dotenv>=1.0",
    "google-cloud-storage>=2.18",
    "google-cloud-pubsub>=2.25",
    "google-cloud-bigquery>=3.25",
]

[dependency-groups]
dev = ["ruff>=0.6", "pytest>=8.3", "pytest-django>=4.9"]
EOF

# --- ai_service pyproject ---------------------------------------------------
info "Writing ai_service/pyproject.toml"
cat > ai_service/pyproject.toml <<'EOF'
[project]
name = "contract-intel-ai"
version = "0.1.0"
description = "FastAPI AI microservice: LangGraph agent + ChromaDB RAG"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "python-dotenv>=1.0",
    "langgraph>=0.2",
    "langchain-google-vertexai>=2.0",
    "chromadb>=0.5",
    "sentence-transformers>=3.2",
    "pypdf>=5.0",
    "pdfplumber>=0.11",
    "google-cloud-storage>=2.18",
    "google-cloud-pubsub>=2.25",
    "google-cloud-bigquery>=3.25",
]

[dependency-groups]
dev = ["ruff>=0.6", "pytest>=8.3", "httpx>=0.27"]
EOF

# --- placeholder entrypoints ------------------------------------------------
info "Writing placeholder entrypoints"
cat > ai_service/app/main.py <<'EOF'
"""FastAPI entrypoint. Real /process endpoint arrives in Phase 3."""
from fastapi import FastAPI

app = FastAPI(title="Contract Intelligence AI Service")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
EOF

cat > django_app/README.md <<'EOF'
# Django product layer
Scaffolded in Phase 1 (`django-admin startproject config .`).
EOF

# --- .env.example -----------------------------------------------------------
info "Writing .env.example"
cat > .env.example <<'EOF'
# ---- Copy to .env and fill in. .env is git-ignored. ----------------------
# Core GCP (from gcp_bootstrap.sh output)
GCP_PROJECT_ID=
GCP_REGION=asia-south1
VERTEX_LOCATION=us-central1
DJANGO_SA_EMAIL=
AI_SA_EMAIL=

# Django
DJANGO_SECRET_KEY=dev-only-change-me
DJANGO_DEBUG=1
# Local Postgres via docker-compose (added in Phase 2). Prod = Cloud SQL.
DATABASE_URL=postgres://ci:ci@localhost:5432/contract_intel
# Shared secret Django uses to verify the processed-event callback (Phase 6)
DJANGO_CALLBACK_SECRET=dev-only-change-me

# Storage & messaging (buckets/topics created in Phase 2)
GCS_BUCKET=
PUBSUB_UPLOAD_TOPIC=document-uploaded
PUBSUB_PROCESSED_TOPIC=document-processed

# Analytics (dataset created in Phase 7)
BQ_DATASET=contract_intel

# Vector store (Phase 4). Local dev uses CHROMA_PATH; prod uses CHROMA_HOST.
CHROMA_PATH=./.chroma
CHROMA_HOST=

# Models (Phase 5). Embeddings run locally on the Chroma server.
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
LLM_EXTRACT_MODEL=gemini-2.5-flash-lite
LLM_RISK_MODEL=gemini-2.5-pro
EOF

# --- .gitignore -------------------------------------------------------------
info "Writing .gitignore"
cat > .gitignore <<'EOF'
# Secrets & local config
.env
*.env.local
# Service-account key files — NEVER commit these
*-key.json
*service-account*.json
gcp-*.json

# Python
__pycache__/
*.py[cod]
.venv/
.uv/
*.egg-info/
.pytest_cache/
.ruff_cache/

# Django
staticfiles/
media/
db.sqlite3

# Vector store persistence
.chroma/
chroma/

# OS / editor
.DS_Store
.idea/
.vscode/
EOF

# --- top-level README -------------------------------------------------------
info "Writing README.md"
cat > README.md <<'EOF'
# Contract Intelligence Platform

Two-service, event-driven contract analysis on GCP.

- `django_app/` — product layer: auth, document/job models, ops admin (Cloud Run)
- `ai_service/` — FastAPI microservice: LangGraph agent + ChromaDB RAG (Cloud Run)
- `infra/`      — gcloud/Terraform scripts, BigQuery DDL, corpus seed scripts
- `scripts/`    — preflight, bootstrap, scaffold

The two services never call each other synchronously — they communicate over
Pub/Sub. See the phase-by-phase build plan for details.

## Getting started
1. `./scripts/preflight_check.sh`
2. edit + run `./scripts/gcp_bootstrap.sh`
3. `cp .env.example .env` and fill in values
4. `gcloud auth application-default login`
EOF

# --- move the helper scripts in if they sit alongside -----------------------
for s in preflight_check.sh gcp_bootstrap.sh; do
  if [ -f "../$s" ]; then cp "../$s" "scripts/$s"; chmod +x "scripts/$s"; fi
done

info "Done. Structure created under ./$ROOT"
command -v tree >/dev/null 2>&1 && tree -a -I '.git' "." || find . -not -path '*/.git/*' | sort
