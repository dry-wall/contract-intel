import json
from unittest.mock import MagicMock, patch

from app.sinks.pubsub_publish import (
    publish_processed_result,
    publish_processing_failed,
    publish_processing_started,
)


def _mock_publisher():
    mock = MagicMock()
    mock.topic_path.return_value = "projects/test/topics/document-processed"
    mock.publish.return_value.result.return_value = "mock-message-id"
    return mock


@patch("app.sinks.pubsub_publish.get_publisher")
def test_publish_processing_started_sends_correct_payload(mock_get_publisher):
    mock_get_publisher.return_value = _mock_publisher()

    message_id = publish_processing_started(job_id=42)

    assert message_id == "mock-message-id"
    call_args = mock_get_publisher.return_value.publish.call_args
    payload = json.loads(call_args[0][1])
    assert payload == {"job_id": 42, "status": "PROCESSING", "result": None, "error_detail": ""}


@patch("app.sinks.pubsub_publish.get_publisher")
def test_publish_processed_result_includes_full_result(mock_get_publisher):
    mock_get_publisher.return_value = _mock_publisher()
    result = {"clauses": [{"clause_type": "X"}], "risk_scores": [], "explanations": []}

    publish_processed_result(job_id=7, result=result)

    call_args = mock_get_publisher.return_value.publish.call_args
    payload = json.loads(call_args[0][1])
    assert payload["job_id"] == 7
    assert payload["status"] == "COMPLETE"
    assert payload["result"] == result


@patch("app.sinks.pubsub_publish.get_publisher")
def test_publish_processing_failed_includes_error_detail(mock_get_publisher):
    mock_get_publisher.return_value = _mock_publisher()

    publish_processing_failed(job_id=9, error_detail="Vertex AI timeout")

    call_args = mock_get_publisher.return_value.publish.call_args
    payload = json.loads(call_args[0][1])
    assert payload["job_id"] == 9
    assert payload["status"] == "FAILED"
    assert payload["error_detail"] == "Vertex AI timeout"
    assert payload["result"] is None
