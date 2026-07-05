# Tracked Gaps / Backlog

## OCR fallback for scanned PDFs (raised after Phase 3 manual test)
- **Symptom:** `pypdf.extract_text()` returns 0 characters for scanned/image-based
  PDFs (confirmed on real upload: 9 pages, 0 chars). This is expected — pypdf
  reads text layers, not pixels.
- **Requirement:** final product must support both text-based and scanned PDFs.
- **Fix:** in app/processing.py, after extraction, if total_chars is near-zero
  relative to page_count, fall back to an OCR pass (e.g. pytesseract over
  page images rendered via pdf2image/pypdfium2, or Google Cloud Vision API's
  document text detection for higher accuracy at a per-page cost).
- **Best point to implement:** when Phase 5's clause extraction tool is wired
  in — that's the point where empty text would silently produce a useless
  result, so it's the natural place to add the "was extraction actually
  successful" check and OCR fallback trigger.
- **Status:** DETECTION implemented in Phase 5 (app/processing.py's
  MIN_CHARS_PER_PAGE guard) — a scanned PDF now returns a clear "needs_ocr"
  status instead of silently wasting an LLM call on empty text. Actual OCR
  fallback (rendering pages to images + pytesseract/Vision API) still not
  built. Not blocking further phases.

## CUAD population coverage gap (found during Phase 4 verification)
- **Finding:** CUAD's 41 categories do NOT include a "Confidentiality" category
  (verified against the real category_descriptions.csv). Its categories focus
  on complex commercial/IP/liability terms (Anti-Assignment, Non-Compete,
  License Grant, Cap on Liability, Governing Law, etc.), not general
  confidentiality boilerplate.
- **Verified behavior:** `retrieve_population()` correctly returns its closest
  available match when queried against a category CUAD doesn't have (e.g. a
  confidentiality clause returns Anti-Assignment as nearest neighbor — not a
  bug, just an honest "no good match" signal). When queried against a category
  CUAD DOES have (e.g. Governing Law), it returns highly accurate matches
  (0.996 similarity, correctly labeled, confirmed on real data).
- **Implication for Phase 5:** the risk-scoring tool's population-benchmarking
  path needs to handle clause_types with no CUAD coverage gracefully — either
  skip the population comparison for those types, or fall back to an
  unfiltered/broader population query rather than trusting a same-category
  match that doesn't actually exist in the data.
- **Status:** tracked here, to be handled explicitly when building Phase 7's
  BigQuery benchmarking (population-side queries only — risk scoring itself,
  which uses the BASELINE side, is unaffected).

## Model availability surprise (found during Phase 5 manual testing)
- **Finding:** `gemini-3.1-flash-lite`, despite being documented as GA,
  returned a 404 "Publisher Model not found" via Vertex AI's regional
  endpoint (us-central1) using langchain-google-vertexai's ChatVertexAI.
  Confirmed as a wider real-world issue (matching reports from other users
  in different regions), not specific to this project/account.
- **Fix applied:** reverted LLM_EXTRACT_MODEL to `gemini-2.5-flash-lite`,
  same generation as the already-working `gemini-2.5-pro`, confirmed
  working via real Gemini calls.
- **Status:** resolved for now. Revisit `gemini-3.1-flash-lite` later,
  possibly with `VERTEX_LOCATION=global` instead of a regional endpoint,
  once broader availability is confirmed.
