"""
Tests for OCR fallback (Phase 11). Mocks both PyMuPDF (fitz) and the Vision
API client — no real PDF rendering or API calls happen here.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.ocr import ocr_pdf


def _mock_fitz_doc(num_pages):
    doc = MagicMock()
    doc.__len__.return_value = num_pages
    pages = []
    for i in range(num_pages):
        page = MagicMock()
        pix = MagicMock()
        pix.tobytes.return_value = f"fake-png-bytes-page-{i}".encode()
        page.get_pixmap.return_value = pix
        pages.append(page)
    doc.__getitem__.side_effect = lambda i: pages[i]
    return doc


@patch("app.ocr._get_vision_client")
@patch("app.ocr.fitz.open")
def test_ocr_pdf_returns_text_per_page(mock_fitz_open, mock_get_client):
    mock_fitz_open.return_value = _mock_fitz_doc(2)

    mock_client = MagicMock()

    def document_text_detection(image):
        response = MagicMock()
        response.error.message = ""
        if b"page-0" in image.content:
            response.full_text_annotation.text = "OCR'd text from page 1"
        else:
            response.full_text_annotation.text = "OCR'd text from page 2"
        return response

    mock_client.document_text_detection.side_effect = document_text_detection
    mock_get_client.return_value = mock_client

    result = ocr_pdf(b"fake-pdf-bytes")

    assert len(result) == 2
    assert result[0] == {"page_number": 1, "text": "OCR'd text from page 1"}
    assert result[1] == {"page_number": 2, "text": "OCR'd text from page 2"}


@patch("app.ocr._get_vision_client")
@patch("app.ocr.fitz.open")
def test_ocr_pdf_raises_loudly_on_vision_api_error(mock_fitz_open, mock_get_client):
    mock_fitz_open.return_value = _mock_fitz_doc(1)

    mock_client = MagicMock()
    response = MagicMock()
    response.error.message = "Quota exceeded"
    mock_client.document_text_detection.return_value = response
    mock_get_client.return_value = mock_client

    with pytest.raises(RuntimeError, match="Quota exceeded"):
        ocr_pdf(b"fake-pdf-bytes")
