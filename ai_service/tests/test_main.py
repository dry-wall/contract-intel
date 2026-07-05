import base64
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _envelope(payload: dict) -> dict:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return {"message": {"data": data, "messageId": "test-msg-1"}, "subscription": "test-sub"}


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("app.main.handle_upload_event")
def test_process_push_acks_and_schedules_background_processing(mock_handle):
    payload = {
        "job_id": 1,
        "document_id": 1,
        "gcs_path": "raw/org1/a.pdf",
        "doc_type": "NDA",
        "organization_id": 1,
    }
    resp = client.post("/process", json=_envelope(payload))

    assert resp.status_code == 200
    assert resp.json() == {"ack": True, "job_id": 1}
    # TestClient runs BackgroundTasks synchronously as part of the request,
    # so by the time we get here handle_upload_event must have been called.
    mock_handle.assert_called_once()
    called_payload = mock_handle.call_args[0][0]
    assert called_payload.job_id == 1
    assert called_payload.gcs_path == "raw/org1/a.pdf"


def test_process_push_rejects_missing_message_field():
    resp = client.post("/process", json={"not_message": {}})
    assert resp.status_code == 400


def test_process_push_rejects_bad_payload_shape():
    # Valid base64/JSON, but missing required ProcessRequest fields.
    resp = client.post("/process", json=_envelope({"job_id": 1}))
    assert resp.status_code == 400
