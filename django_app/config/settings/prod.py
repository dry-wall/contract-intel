"""
Production settings. DJANGO_SETTINGS_MODULE=config.settings.prod
Wired fully in Phase 10 (Cloud Run + Cloud SQL connector + Secret Manager).
Left here now so the three-file split exists from day one.
"""
import os

from .base import *  # noqa: F401,F403

DEBUG = False

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
