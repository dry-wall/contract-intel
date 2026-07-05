"""
Central config for the AI service, loaded once at import time. Mirrors the
Django settings pattern: everything comes from environment variables via
.env, so the same code works unmodified against local emulators or real GCP.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# ai_service/app/config.py -> ai_service/ -> repo root, where .env lives.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ.get("GCP_REGION", "asia-south1")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_EMULATOR_HOST = os.environ.get("GCS_EMULATOR_HOST", "")  # dev only

PUBSUB_UPLOAD_TOPIC = os.environ.get("PUBSUB_UPLOAD_TOPIC", "document-uploaded")
PUBSUB_PROCESSED_TOPIC = os.environ.get("PUBSUB_PROCESSED_TOPIC", "document-processed")
# Pull subscription used for LOCAL DEV only. Prod (Phase 10) switches to a
# push subscription hitting the /process endpoint in main.py instead — the
# processing logic in processing.py is identical either way.
PUBSUB_UPLOAD_PULL_SUBSCRIPTION = os.environ.get(
    "PUBSUB_UPLOAD_PULL_SUBSCRIPTION", "ai-process-pull-sub"
)
# PUBSUB_EMULATOR_HOST is read directly by google-cloud-pubsub itself; we
# don't need to reference it here, just make sure load_dotenv() above has
# already populated it into os.environ before any pubsub client is built.
