from unittest.mock import patch

from app.processing import MIN_CHARS_PER_PAGE, _processed_job_ids, handle_upload_event
from app.schemas.process import ProcessRequest


def _payload(job_id=1, doc_type="MSA"):
    return ProcessRequest(
        job_id=job_id, document_id=100 + job_id, gcs_path=f"raw/org1/doc{job_id}.pdf",
        doc_type=doc_type, organization_id=1,
    )


def setup_function():
    _processed_job_ids.clear()


@patch("app.processing.stream_clauses")
@patch("app.processing.publish_processed_result")
@patch("app.processing.publish_processing_started")
@patch("app.processing.run_agent")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_success_path_publishes_started_then_complete(
    mock_extract, mock_download, mock_run_agent, mock_started, mock_complete, mock_stream
):
    good_text = "x" * (MIN_CHARS_PER_PAGE * 10)
    mock_extract.return_value = [{"page_number": 1, "text": good_text}]
    mock_download.return_value = b"fake"
    mock_run_agent.return_value = {"clauses": [{"clause_type": "X"}], "risk_scores": [], "explanations": []}

    result = handle_upload_event(_payload(job_id=1))

    assert result["status"] == "processed"
    mock_started.assert_called_once_with(1)
    mock_complete.assert_called_once()
    assert mock_complete.call_args[0][0] == 1  # job_id
    assert mock_complete.call_args[0][1]["clauses"] == [{"clause_type": "X"}]
    assert 1 in _processed_job_ids

    # Phase 7: BigQuery streaming must also fire on success, with the same clauses/risk_scores.
    mock_stream.assert_called_once()
    assert mock_stream.call_args[1]["job_id"] == 1
    assert mock_stream.call_args[1]["clauses"] == [{"clause_type": "X"}]


@patch("app.processing.publish_processing_failed")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_scanned_pdf_publishes_failed_and_is_not_marked_processed(
    mock_extract, mock_download, mock_failed
):
    mock_extract.return_value = [{"page_number": i, "text": ""} for i in range(1, 6)]
    mock_download.return_value = b"fake"

    result = handle_upload_event(_payload(job_id=2))

    assert result["status"] == "needs_ocr"
    mock_failed.assert_called_once()
    assert mock_failed.call_args[0][0] == 2
    assert "scanned" in mock_failed.call_args[0][1].lower()
    # Critical: NOT marked as processed, so a future redelivery isn't silently skipped.
    assert 2 not in _processed_job_ids


@patch("app.processing.stream_clauses")
@patch("app.processing.publish_processed_result")
@patch("app.processing.publish_processing_failed")
@patch("app.processing.publish_processing_started")
@patch("app.processing.run_agent")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_agent_exception_publishes_failed_and_allows_retry(
    mock_extract, mock_download, mock_run_agent, mock_started, mock_failed, mock_complete, mock_stream
):
    good_text = "x" * (MIN_CHARS_PER_PAGE * 10)
    mock_extract.return_value = [{"page_number": 1, "text": good_text}]
    mock_download.return_value = b"fake"
    mock_run_agent.side_effect = RuntimeError("Vertex AI is temporarily unavailable")

    result = handle_upload_event(_payload(job_id=3))

    assert result["status"] == "failed"
    mock_failed.assert_called_once_with(3, "Vertex AI is temporarily unavailable")
    # Critical: NOT marked as processed. A redelivery of the same message
    # (or a manual admin requeue) must actually retry, not be silently skipped.
    assert 3 not in _processed_job_ids

    # Prove the retry actually works: call it again with the agent now succeeding.
    mock_run_agent.side_effect = None
    mock_run_agent.return_value = {"clauses": [], "risk_scores": [], "explanations": []}
    second_result = handle_upload_event(_payload(job_id=3))
    assert second_result["status"] == "processed"
    assert mock_run_agent.call_count == 2  # genuinely retried, not skipped


@patch("app.processing.stream_clauses")
@patch("app.processing.publish_processed_result")
@patch("app.processing.publish_processing_started")
@patch("app.processing.run_agent")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_duplicate_delivery_after_success_is_skipped(
    mock_extract, mock_download, mock_run_agent, mock_started, mock_complete, mock_stream
):
    good_text = "x" * (MIN_CHARS_PER_PAGE * 10)
    mock_extract.return_value = [{"page_number": 1, "text": good_text}]
    mock_download.return_value = b"fake"
    mock_run_agent.return_value = {"clauses": [], "risk_scores": [], "explanations": []}

    first = handle_upload_event(_payload(job_id=4))
    second = handle_upload_event(_payload(job_id=4))

    assert first["status"] == "processed"
    assert second["status"] == "skipped_duplicate"
    mock_run_agent.assert_called_once()  # only called once, real duplicate correctly skipped
