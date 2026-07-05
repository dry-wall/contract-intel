"""
Creates the GCS bucket used for raw PDF storage, if it doesn't already exist.
Works identically against fake-gcs-server (dev) and real GCS (prod) — the
storage.get_storage_client() helper decides which one based on
GCS_EMULATOR_HOST. Safe to run repeatedly.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from documents.storage import get_storage_client


class Command(BaseCommand):
    help = "Creates the GCS_BUCKET if it does not already exist."

    def handle(self, *args, **options):
        if not settings.GCS_BUCKET:
            self.stderr.write("GCS_BUCKET is not set in .env — nothing to do.")
            return

        client = get_storage_client()
        if client.lookup_bucket(settings.GCS_BUCKET) is not None:
            self.stdout.write(self.style.SUCCESS(f"Bucket '{settings.GCS_BUCKET}' already exists."))
            return

        client.create_bucket(settings.GCS_BUCKET, location=settings.GCP_REGION)
        self.stdout.write(self.style.SUCCESS(f"Bucket '{settings.GCS_BUCKET}' created."))
