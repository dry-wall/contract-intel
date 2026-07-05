"""
Uses pypdf itself to generate a tiny real PDF in-memory, so extraction is
tested against an actual valid PDF structure rather than a hand-typed byte
string that might not be representative.
"""
from io import BytesIO

from pypdf import PdfWriter

from app.pdf_extract import extract_pages


def _make_pdf_bytes(num_pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_pages_returns_one_entry_per_page():
    pdf_bytes = _make_pdf_bytes(num_pages=3)
    pages = extract_pages(pdf_bytes)

    assert len(pages) == 3
    assert [p["page_number"] for p in pages] == [1, 2, 3]
    # Blank pages extract to empty text — just confirming no crash and the
    # right shape, not asserting on content.
    assert all("text" in p for p in pages)
