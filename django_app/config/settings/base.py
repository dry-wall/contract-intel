"""
Base settings shared by dev.py and prod.py. Never import this directly —
DJANGO_SETTINGS_MODULE always points at config.settings.dev or
config.settings.prod, both of which start with `from .base import *`.
"""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# BASE_DIR = django_app/ (three levels up from config/settings/base.py:
# base.py -> settings/ -> config/ -> django_app/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# Repo root (one level above django_app/) is where .env lives.
REPO_ROOT = BASE_DIR.parent
load_dotenv(REPO_ROOT / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # local apps
    "accounts",
    "documents",
    "analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Custom user model -------------------------------------------------
# MUST be set before the first migration ever runs. Points at the
# Organization-aware User defined in accounts/models.py.
AUTH_USER_MODEL = "accounts.User"

# --- Database ------------------------------------------------------------
# Single source of truth: DATABASE_URL from .env. Local dev -> docker-compose
# Postgres. Production -> Cloud SQL via the connector (set differently in
# prod.py). conn_max_age keeps connections alive briefly between requests.
DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
# --- GCP resource config (Phase 2 onward) ---------------------------------
# GCP_PROJECT_ID is required everywhere (storage, pubsub, bigquery, vertex).
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ.get("GCP_REGION", "asia-south1")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
PUBSUB_UPLOAD_TOPIC = os.environ.get("PUBSUB_UPLOAD_TOPIC", "document-uploaded")
PUBSUB_PROCESSED_TOPIC = os.environ.get("PUBSUB_PROCESSED_TOPIC", "document-processed")
# Pull subscription for local dev only -- Phase 10 uses a push subscription instead.
PUBSUB_PROCESSED_PULL_SUBSCRIPTION = os.environ.get(
    "PUBSUB_PROCESSED_PULL_SUBSCRIPTION", "django-processed-pull-sub"
)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))  # 25MB default
# --- BigQuery (Phase 7) ------------------------------------------------------
BQ_DATASET = os.environ.get("BQ_DATASET", "contract_intel")
