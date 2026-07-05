"""
Cloud Storage read access for the AI worker. Mirrors documents/storage.py on
the Django side, but this service only ever READS (google-cloud-storage
client here never needs write access — the ai-worker-sa service account is
scoped to storage.objectViewer only, by design).
"""
from google.cloud import storage

from app import config

_client: storage.Client | None = None


def get_storage_client() -> storage.Client:
    global _client
    if _client is not None:
        return _client

    if config.GCS_EMULATOR_HOST:
        from google.auth.credentials import AnonymousCredentials

        _client = storage.Client(
            project=config.GCP_PROJECT_ID,
            credentials=AnonymousCredentials(),
            client_options={"api_endpoint": config.GCS_EMULATOR_HOST},
        )
    else:
        _client = storage.Client(project=config.GCP_PROJECT_ID)
    return _client


def download_pdf(gcs_path: str) -> bytes:
    """gcs_path is the object key ONLY (e.g. 'raw/org1/abcd.pdf'), matching
    exactly what Document.gcs_path stores on the Django side — no gs:// prefix."""
    bucket = get_storage_client().bucket(config.GCS_BUCKET)
    blob = bucket.blob(gcs_path)
    return blob.download_as_bytes()
