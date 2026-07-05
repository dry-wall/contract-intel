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


@patch("app.processing.run_agent")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_scanned_pdf_short_circuits_before_calling_agent(mock_extract, mock_download, mock_run_agent):
    # Simulate a scanned PDF: 5 pages, almost no extracted text.
    mock_extract.return_value = [{"page_number": i, "text": ""} for i in range(1, 6)]
    mock_download.return_value = b"fake pdf bytes"

    result = handle_upload_event(_payload(job_id=1))

    assert result["status"] == "needs_ocr"
    mock_run_agent.assert_not_called()  # must NOT spend an LLM call on empty text


@patch("app.processing.run_agent")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_normal_pdf_calls_agent_and_returns_full_result(mock_extract, mock_download, mock_run_agent):
    good_text = "x" * (MIN_CHARS_PER_PAGE * 10)  # comfortably above the threshold
    mock_extract.return_value = [{"page_number": 1, "text": good_text}]
    mock_download.return_value = b"fake pdf bytes"
    mock_run_agent.return_value = {
        "clauses": [{"clause_type": "Governing Law", "text": "...", "page": 1}],
        "risk_scores": [],
        "explanations": [],
    }

    result = handle_upload_event(_payload(job_id=2, doc_type="NDA"))

    assert result["status"] == "processed"
    mock_run_agent.assert_called_once()
    called_pages, called_kwargs_doc_type = mock_run_agent.call_args[0][0], mock_run_agent.call_args[1]["doc_type"]
    assert called_kwargs_doc_type == "NDA"
    assert result["clauses"][0]["clause_type"] == "Governing Law"


@patch("app.processing.run_agent")
@patch("app.processing.download_pdf")
@patch("app.processing.extract_pages")
def test_duplicate_job_id_skips_reprocessing_even_with_real_agent_wired(
    mock_extract, mock_download, mock_run_agent
):
    good_text = "x" * (MIN_CHARS_PER_PAGE * 10)
    mock_extract.return_value = [{"page_number": 1, "text": good_text}]
    mock_download.return_value = b"fake pdf bytes"
    mock_run_agent.return_value = {"clauses": [], "risk_scores": [], "explanations": []}

    first = handle_upload_event(_payload(job_id=3))
    second = handle_upload_event(_payload(job_id=3))

    assert first["status"] == "processed"
    assert second["status"] == "skipped_duplicate"
    mock_run_agent.assert_called_once()  # NOT called twice — this is now an LLM-cost guard, not just a text-extract guard
