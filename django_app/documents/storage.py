"""
Cloud Storage helper. Stores only raw PDF bytes; the Document model stores
the returned gcs_path string, never the file content.

Environment-aware: if GCS_EMULATOR_HOST is set (local dev, pointed at
fake-gcs-server via docker-compose), the client talks to the emulator over
plain HTTP with anonymous credentials. In prod, GCS_EMULATOR_HOST is unset
and the client uses real GCS with ADC / the Cloud Run service account.
Application code (upload_pdf) never needs to know which mode it's in.
"""
import os
import uuid

from django.conf import settings
from google.cloud import storage

_client: storage.Client | None = None


def get_storage_client() -> storage.Client:
    global _client
    if _client is not None:
        return _client

    emulator_host = os.environ.get("GCS_EMULATOR_HOST")
    if emulator_host:
        # fake-gcs-server needs anonymous credentials + a custom endpoint.
        from google.auth.credentials import AnonymousCredentials

        _client = storage.Client(
            project=settings.GCP_PROJECT_ID,
            credentials=AnonymousCredentials(),
            client_options={"api_endpoint": emulator_host},
        )
    else:
        _client = storage.Client(project=settings.GCP_PROJECT_ID)
    return _client


def upload_pdf(file_obj, organization_id: int) -> str:
    """
    Uploads an in-memory/temp uploaded PDF to GCS and returns the object
    path (e.g. "raw/org7/ab12cd34.pdf") — NOT a full gs:// URL. Document.gcs_path
    stores exactly this string.
    """
    key = f"raw/org{organization_id}/{uuid.uuid4().hex}.pdf"
    bucket = get_storage_client().bucket(settings.GCS_BUCKET)
    blob = bucket.blob(key)
    file_obj.seek(0)
    blob.upload_from_file(file_obj, content_type="application/pdf")
    return key
