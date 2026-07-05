"""Local development settings. DJANGO_SETTINGS_MODULE=config.settings.dev"""
import os

from .base import *  # noqa: F401,F403

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Verbose console logging in dev so job state transitions are visible while
# you develop the upload/processing flow in later phases.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
