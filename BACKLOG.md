# Tracked Gaps / Backlog

## OCR fallback for scanned PDFs (raised after Phase 3 manual test)
- **Status: RESOLVED (Phase 11).** Implemented via `ai_service/app/ocr.py`:
  each page of a scanned/low-text PDF is rendered to an image locally
  (PyMuPDF) and run through Google Cloud Vision's synchronous
  `document_text_detection` per page — avoiding Vision's async-only native
  PDF workflow (which requires a GCS round-trip for both input and output).
  Wired into `processing.py`'s existing char-count guard: instead of
  dead-ending with a FAILED event, a low-text document now falls through to
  OCR and continues the normal pipeline on success. An OCR failure itself
  still fails loudly and stays retryable (not marked processed), same
  pattern as every other failure path in this function. 2 new tests for
  `ocr.py`, 2 new tests for the `processing.py` integration, all passing.
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
- **Status: RESOLVED (Phase 11).** `risk_scoring.py` now processes clauses
  concurrently via a bounded `ThreadPoolExecutor` (`MAX_WORKERS = 5`) —
  each clause's Chroma query + Gemini Pro call is I/O-bound, so threads
  genuinely parallelize wall-clock time by releasing the GIL during network
  waits. Results are reassembled by `clause_index` regardless of which
  clause's work finishes first — verified with a test that deliberately
  makes later clauses complete before earlier ones (artificial delays) to
  prove the ordering guarantee holds under genuine out-of-order completion,
  not just "happens to work in submission order." Bounded concurrency
  (not unbounded) avoids firing e.g. 100 simultaneous Gemini requests for a
  100-clause document and blowing through rate limits. 5 tests, all passing.
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

## Push webhook OIDC audience validation skipped (Phase 10)
- **Status: RESOLVED (Phase 11).** Now that the Cloud Run service URL is
  stable, `DJANGO_PUSH_AUDIENCE` is set to the real deployed URL and passed
  as the `audience` parameter to `id_token.verify_oauth2_token()`. Falls
  back to `None` (no strict audience check) only if the setting is left
  unset, so local/dev environments without a real URL still work. 2 new
  tests confirm the audience is actually passed when configured and
  correctly `None` when not — 8 total tests on the webhook, all passing.
- **Finding:** `processed_event_webhook`'s OIDC verification calls
  `id_token.verify_oauth2_token(token, google_requests.Request())` without
  passing an `audience` argument, meaning it confirms the token was issued
  by Google and identifies the expected service account, but does NOT
  confirm the token was minted specifically for THIS webhook's URL. A valid
  OIDC token for `ai-worker-sa` minted for a different audience would
  currently still pass.
- **Why deferred:** the webhook's own URL isn't known until after the
  first `gcloud run deploy` completes — a genuine chicken-and-egg problem
  for a value that would otherwise be hardcoded into the code that gets
  deployed to produce that same URL.
- **Fix (tracked, not yet built):** after first deploy, capture `$DJANGO_URL`
  and either (a) pass it explicitly as the `audience` parameter via an env
  var (`DJANGO_PUSH_AUDIENCE`) read by the view, or (b) use a custom domain
  mapped to the Cloud Run service so the audience value is stable across
  redeploys instead of changing with every new revision URL.
- **Status:** open, tracked for Phase 11 hardening. Not a severe risk today
  given the additional service-account-identity check already in place, but
  worth closing before this handles anything beyond a demo/portfolio project.

## ChromaDB persistent server has no real scaling/durability story (Phase 10)
- **Finding:** `chroma-server` is deployed with `--min-instances=1
  --max-instances=1` because Chroma's data lives in the container's own
  local storage — no persistent volume, no replication. This satisfies the
  Phase 4 decision ("persistent server, not on-disk client") only in the
  narrow sense of "the process doesn't restart on every request"; it does
  NOT protect against data loss if the container is ever rescheduled,
  crashes, or the underlying VM is reclaimed by Cloud Run's infrastructure.
- **Why deferred:** implementing a genuinely durable backing store (a
  persistent disk mounted into Cloud Run, or migrating to a managed vector
  DB / Chroma Cloud) is real scope beyond a demo/portfolio deployment, and
  the corpus itself (Phase 4's seeded baseline + population clauses) is
  fully reproducible by re-running `infra/seed_corpus.py` +
  `infra/embed_and_load.py` if it were ever lost — an acceptable risk for
  now, not for a real production tenant-facing system.
- **Fix (tracked, not yet built):** mount a persistent volume (Cloud Run's
  volume mount support) or migrate to a managed alternative before this
  system holds any data that isn't trivially re-derivable from the seed
  scripts.
- **Status:** open, tracked for Phase 11 hardening.

## Cloud Run CPU throttling caused silent hangs in background processing (Phase 10)
- **Symptom:** in production, every upload correctly returned `200 OK` from
  `ai-service`'s `/process` endpoint, but the actual background work
  (Gemini calls, embedding model loading, Chroma queries) would then hang
  indefinitely with zero errors, zero timeouts firing, and normal-looking
  memory usage (~40% peak, confirmed via Cloud Monitoring). Jobs got stuck
  at PROCESSING forever.
- **Root cause:** Cloud Run's default CPU allocation is request-scoped —
  CPU is only guaranteed to be available while actively handling an HTTP
  request. Since `/process` deliberately returns its response immediately
  and does the real work afterward via FastAPI `BackgroundTasks` (Phase 3's
  design, so Pub/Sub doesn't see a slow response and retry), the container
  could be throttled to near-zero CPU the moment the response was sent —
  starving the background work indefinitely, with no crash or error to
  surface, since nothing was actually broken, just never scheduled to run.
- **Why it was hard to find:** every symptom (silent hang, no traceback,
  intermittent-looking behavior across different runs) pointed toward the
  code itself — auth, SSL, tokenizer threading, resource exhaustion — and
  several real, worthwhile hardening fixes were made chasing those leads
  (see below) before the actual cause was isolated. A standalone Cloud Run
  **Job** running the identical embedding-load code succeeded in 1 second,
  which was the key piece of evidence: Jobs aren't subject to request-scoped
  CPU throttling, so an environment that behaves differently between Jobs
  and Services pointed straight at Cloud Run's CPU allocation model rather
  than application code.
- **Fix:** `gcloud run services update ai-service --no-cpu-throttling` —
  CPU is now allocated for the container's full lifetime, not just during
  active requests. This is the standard, documented setting for exactly
  this background-processing pattern.
- **Also changed along the way, worth keeping regardless:**
  - `pubsub_publish.py`: publish timeout raised (10s -> 30s) — real fix,
    `ai-worker-sa` was also found to be missing `roles/pubsub.publisher` on
    both topics entirely (granted during this session).
  - `retrieval.py`: `chromadb.HttpClient` now uses `ssl=True` and attaches
    a real OIDC bearer token — necessary regardless of the CPU-throttling
    bug, since `chroma-server` is genuinely `--no-allow-unauthenticated`.
    Known limitation: the token is fetched once per client instance and
    not refreshed — will start failing again after ~1 hour on a
    long-lived warm instance. Tracked as its own follow-up below.
  - `gcs.py`: `download_pdf` now wrapped with an explicit 30s timeout
    instead of no timeout at all — good defensive practice independent of
    this bug.
- **Status:** root cause fixed and confirmed working end-to-end in
  production. Follow-ups below are not yet done.

## Follow-ups from the CPU-throttling investigation (Phase 11) — all resolved
- **`--concurrency=1` was overly conservative.** RESOLVED: raised to 20
  now that `--no-cpu-throttling` is the actual fix in place.
- **Chroma OIDC token refresh.** RESOLVED: `retrieval.py`'s `_get_client()`
  now rebuilds the client (fetching a fresh token) whenever the cached
  token is older than 45 minutes, safely under the ~1hr token lifetime.
  4 tests confirm: first call fetches a token, a second call with a fresh
  token does NOT re-fetch (no wasted calls), a stale token DOES trigger a
  genuine rebuild (not just a cache hit), and the no-CHROMA_HOST local-dev
  path is unaffected. The Phase 10 diagnostic subprocess probe (added
  during the CPU-throttling investigation, no longer needed) was removed
  in the same pass — it added a full subprocess spawn to every cold start
  for no benefit once the real bug was found.
- **`processed_event_webhook`'s audience check** — see its own entry above,
  now resolved in the same phase.

## Phase 11 additions (not backlog items, but worth recording)
- **Dead-letter queue alerting**: a Cloud Monitoring alert policy now fires
  (via email notification channel) if either `document-uploaded-dlq` or
  `document-processed-dlq` ever receives a message — previously a
  permanently-stuck message would fail silently forever.
- **CI**: GitHub Actions now runs both test suites (`ai_service` and
  `django_app`) on every push and PR to `main`. Two real CI-specific gaps
  were found and fixed getting this working: (1) `ai_service`'s tests need
  `GCP_PROJECT_ID` and related env vars explicitly set in the workflow,
  since `app/config.py` reads them as required (no default) and CI has no
  `.env` file the way local dev does; (2) Django's tests need
  `collectstatic` run first, since Phase 8's WhiteNoise
  `CompressedManifestStaticFilesStorage` requires a manifest file that only
  gets generated by `collectstatic` — locally this was masked because the
  manifest already existed on disk from an earlier Docker build.
