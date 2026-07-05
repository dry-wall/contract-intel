from unittest.mock import patch

from app.processing import _processed_job_ids, handle_upload_event
from app.schemas.process import ProcessRequest
from app.pdf_extract import extract_pages
from tests.test_pdf_extract import _make_pdf_bytes


def _payload(job_id=1):
    return ProcessRequest(
        job_id=job_id,
        document_id=100 + job_id,
        gcs_path=f"raw/org1/doc{job_id}.pdf",
        doc_type="NDA",
        organization_id=1,
    )


def setup_function():
    _processed_job_ids.clear()


@patch("app.processing.download_pdf")
def test_handle_upload_event_extracts_and_marks_processed(mock_download):
    mock_download.return_value = _make_pdf_bytes(num_pages=2)

    result = handle_upload_event(_payload(job_id=1))

    assert result["status"] == "extracted"
    assert result["page_count"] == 2
    assert 1 in _processed_job_ids
    mock_download.assert_called_once_with("raw/org1/doc1.pdf")


@patch("app.processing.download_pdf")
def test_duplicate_delivery_is_skipped_without_re_downloading(mock_download):
    mock_download.return_value = _make_pdf_bytes(num_pages=1)

    first = handle_upload_event(_payload(job_id=2))
    second = handle_upload_event(_payload(job_id=2))

    assert first["status"] == "extracted"
    assert second["status"] == "skipped_duplicate"
    # download_pdf must only be called once — the whole point of the guard.
    mock_download.assert_called_once()
