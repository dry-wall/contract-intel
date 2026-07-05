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
- **Status:** tracked here, to be handled explicitly when building Phase 5's
  risk-scoring tool.

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

## Sequential risk-scoring doesn't scale to large documents (found during Phase 6 manual testing)
- **Symptom:** a 71-page document with many clauses took long enough that the
  ai_service pull subscription's ack deadline (even after raising it to 600s)
  was exceeded, causing Pub/Sub to redeliver the original document-uploaded
  message WHILE the first attempt was still running. Because
  _processed_job_ids only marks a job done on success (correct behavior, see
  the idempotency-on-failure fix in Phase 6), the redelivered attempt was not
  caught by the duplicate guard — both attempts ran concurrently, each
  independently calling Gemini for the same job_id. Not data-corrupting
  (Django's mark_complete is safe to call twice) but wasted real LLM spend.
- **Likely root cause:** the Pub/Sub client library normally auto-extends a
  message's ack deadline in a background thread while the callback is still
  running. sentence-transformers/PyTorch's local embedding computation is
  CPU-bound and can hold the GIL for extended periods, likely starving that
  background thread and preventing the auto-extension from firing — the
  redelivery landed almost exactly at the configured deadline, not at some
  arbitrary time, which supports this theory over "just needs a longer
  deadline."
- **Mitigation applied:** set `flow_control=pubsub_v1.types.FlowControl(max_messages=1)`
  on the ai_service pull subscriber (app/pull_worker.py), forcing strictly
  sequential message processing. This eliminates the concurrent-duplicate-
  processing symptom (verified: a short document now goes PROCESSING ->
  COMPLETE exactly once, no duplicates). It does NOT fix the underlying
  slowness for large documents — a large enough document could still exceed
  the ack deadline and trigger a redelivery, it just can no longer overlap
  with a still-running attempt on itself.
- **Root fix (tracked, not yet built):** parallelize the risk-scoring loop in
  app/tools/risk_scoring.py (e.g. asyncio or a thread/process pool) so a
  document with many clauses finishes in seconds rather than minutes, well
  under any reasonable ack deadline. Also worth investigating running
  embeddings in a separate process (not sharing the GIL with the Pub/Sub
  client's lease-management thread) if the GIL-contention theory holds up.
- **Status:** mitigated (no more duplicate concurrent processing). Root
  fix (parallelization) still open, tracked for Phase 11 hardening.
