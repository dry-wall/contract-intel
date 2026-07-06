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
@patch("app.processing.ocr_pdf")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_scanned_pdf_falls_back_to_ocr_and_completes(
    mock_extract, mock_download, mock_ocr, mock_run_agent, mock_started, mock_complete, mock_stream
):
    mock_extract.return_value = [{"page_number": i, "text": ""} for i in range(1, 4)]
    mock_download.return_value = b"fake"
    good_text = "x" * (MIN_CHARS_PER_PAGE * 10)
    mock_ocr.return_value = [{"page_number": 1, "text": good_text}]
    mock_run_agent.return_value = {"clauses": [{"clause_type": "X"}], "risk_scores": [], "explanations": []}

    result = handle_upload_event(_payload(job_id=1))

    assert result["status"] == "processed"
    mock_ocr.assert_called_once_with(b"fake")
    mock_complete.assert_called_once()
    assert 1 in _processed_job_ids


@patch("app.processing.publish_processing_failed")
@patch("app.processing.ocr_pdf")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_ocr_failure_is_reported_and_retryable(
    mock_extract, mock_download, mock_ocr, mock_failed
):
    mock_extract.return_value = [{"page_number": 1, "text": ""}]
    mock_download.return_value = b"fake"
    mock_ocr.side_effect = RuntimeError("Vision API quota exceeded")

    result = handle_upload_event(_payload(job_id=2))

    assert result["status"] == "ocr_failed"
    mock_failed.assert_called_once()
    assert "Vision API quota exceeded" in mock_failed.call_args[0][1]
    assert 2 not in _processed_job_ids
