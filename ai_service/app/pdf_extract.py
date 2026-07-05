"""
Raw PDF text extraction. Keeps page boundaries because Phase 5's clause
extraction tool benefits from knowing which page each clause came from.
Uses pypdf — pure Python, no system dependencies, fine for text-heavy
contracts. (pdfplumber is also in pyproject.toml for later phases if a
contract needs table/layout-aware extraction; not needed yet.)
"""
from io import BytesIO

from pypdf import PdfReader


def extract_pages(pdf_bytes: bytes) -> list[dict]:
    """Returns [{"page_number": 1, "text": "..."}, ...], 1-indexed."""
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        pages.append({"page_number": i, "text": page.extract_text() or ""})
    return pages
