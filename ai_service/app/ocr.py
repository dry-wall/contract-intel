"""
OCR fallback for scanned/image-only PDFs (Phase 11 — closes the backlog
item open since Phase 5, when the MIN_CHARS_PER_PAGE guard in
processing.py detected these but had no real fallback, just a FAILED
event).

Vision API's native PDF text detection is async-only (files:asyncBatchAnnotate,
requiring a GCS round-trip for both input and output — see
https://cloud.google.com/vision/docs/pdf). Rather than take on that
complexity, this renders each PDF page to an image locally (PyMuPDF) and
calls Vision's synchronous document_text_detection per page — same
per-page synchronous style as the rest of this pipeline, and no extra GCS
output bucket/parsing to manage.
"""
import io
import logging

import fitz  # PyMuPDF
from google.cloud import vision

logger = logging.getLogger(__name__)

# 200 DPI is a reasonable balance: high enough for Vision's OCR accuracy on
# typical scanned business documents, low enough to keep per-page render +
# upload time and request payload size reasonable.
RENDER_DPI = 200

_vision_client: vision.ImageAnnotatorClient | None = None


def _get_vision_client() -> vision.ImageAnnotatorClient:
    global _vision_client
    if _vision_client is None:
        _vision_client = vision.ImageAnnotatorClient()
    return _vision_client


def ocr_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Renders each page of pdf_bytes to a PNG image and runs Vision API's
    DOCUMENT_TEXT_DETECTION on each page independently. Returns the same
    shape as pdf_extract.extract_pages() — [{"page_number": int, "text": str}]
    — so it's a drop-in replacement wherever regular text extraction failed.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        pix = page.get_pixmap(dpi=RENDER_DPI)
        png_bytes = pix.tobytes("png")

        image = vision.Image(content=png_bytes)
        response = _get_vision_client().document_text_detection(image=image)

        if response.error.message:
            # Fail loudly for this page rather than silently returning
            # empty text — a partial/garbled OCR result is worse than a
            # clear error, since it could look like a real (empty) clause.
            raise RuntimeError(
                f"Vision API error on page {page_index + 1}: {response.error.message}"
            )

        text = response.full_text_annotation.text
        pages.append({"page_number": page_index + 1, "text": text})
        logger.info("ocr_pdf: page %d OCR'd, %d characters", page_index + 1, len(text))

    doc.close()
    return pages
