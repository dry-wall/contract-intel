"""
ProcessRequest is the fixed contract this service expects to receive —
its fields must exactly match the payload published by Django's
documents/pubsub.py:publish_document_uploaded(). Changing a field name here
means changing it on both sides.
"""
from pydantic import BaseModel


class ProcessRequest(BaseModel):
    job_id: int
    document_id: int
    gcs_path: str
    doc_type: str
    organization_id: int
