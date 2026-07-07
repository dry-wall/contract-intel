# Contract Intelligence Platform

An AI-powered contract analysis platform that extracts clauses from legal documents, scores their risk against real market-standard templates using retrieval-augmented generation, and benchmarks every document against the platform's own accumulated history. Built as a two-service, event-driven system on Google Cloud — Django for the product layer, FastAPI + LangGraph for the AI pipeline — communicating exclusively through Pub/Sub.

## What it does

Upload a contract (NDA, MSA, lease, employment agreement, or other) and the platform will:

1. **Extract every clause** using Gemini, categorized by type (Limitation of Liability, Governing Law, Termination, etc.)
2. **Score risk via RAG** — each clause is compared against the closest matching clause in a real corpus of market-standard templates (Common Paper's open-source agreements) and 6,400+ real-world clauses (the CUAD dataset), not scored by an LLM's opinion alone
3. **Explain findings in plain English** — a natural-language summary of what each flagged clause actually means for the person reading it
4. **Benchmark against the population** — see how this document's risk profile compares to every other document the platform has ever processed, via a live BigQuery-backed percentile calculation
5. **Fall back to OCR** for scanned/image-only PDFs via Google Cloud Vision, so non-selectable-text documents still get analyzed

Different document types get different treatment: an NDA skips risk-scoring for its confidentiality clauses (there's no adversarial risk to measure in a document both parties agree to identically), while an MSA gets full risk-scoring across every clause.

## Architecture

```
                    ┌──────────────────────┐
   Browser  ──────▶│   Django (product)   │
                    │  - auth, dashboard   │
                    │  - upload/status/    │
                    │    results pages     │
                    └──────────┬───────────┘
                               │ publish (document-uploaded)
                               ▼
                    ┌──────────────────────┐
                    │      Pub/Sub         │
                    └──────────┬───────────┘
                               │ push
                               ▼
                    ┌──────────────────────┐
                    │  FastAPI + LangGraph │
                    │  - extract clauses   │
                    │  - RAG risk scoring  │──────▶ ChromaDB (ai_service's RAG corpus)
                    │  - explain findings  │
                    │  - OCR fallback      │──────▶ Vision API (scanned PDFs)
                    └──────────┬───────────┘
                               │ publish (document-processed)
                               ▼
                    ┌──────────────────────┐
                    │      Pub/Sub         │
                    └──────────┬───────────┘
                               │ push (webhook, OIDC-verified)
                               ▼
                    ┌─────────────────────┐
                    │   Django (webhook)  │──────▶ BigQuery (population analytics)
                    └─────────────────────┘
```

The two services **never call each other directly** — every interaction happens through Pub/Sub. This means either service can be redeployed, scaled, or fail independently without the other needing to know.

## Why two services, not one

Django owns the product surface: auth, file upload, the results UI, the admin ops dashboard. FastAPI + LangGraph owns the AI pipeline: LLM calls, RAG retrieval, agent orchestration. Splitting them means:

- The AI service can be resourced differently (more memory/CPU for embedding computation) without over-provisioning the web tier
- LangChain/LangGraph/ChromaDB's dependency footprint (including PyTorch) never touches the Django image
- Either side can be redeployed independently — a prompt tweak in the agent doesn't require a Django deploy

## Tech stack

| Layer | Technology |
|---|---|
| Product backend | Django 6, Postgres (Cloud SQL) |
| AI service | FastAPI, LangGraph, LangChain |
| LLMs | Gemini 2.5 Flash-Lite (extraction, explanation), Gemini 2.5 Pro (risk scoring) |
| Vector search | ChromaDB, local `BAAI/bge-small-en-v1.5` embeddings (zero embedding cost) |
| OCR | Google Cloud Vision (`document_text_detection`) + PyMuPDF for page rendering |
| Messaging | Google Cloud Pub/Sub (push subscriptions in prod, pull worker in local dev) |
| Analytics | BigQuery, streamed per-clause after each successful analysis |
| Storage | Google Cloud Storage (raw PDFs), Cloud SQL (metadata + results), a dedicated GCS-FUSE-mounted bucket (ChromaDB's persistent corpus) |
| Frontend | Server-rendered Django templates, vanilla JS for live status polling, Chart.js for the population-benchmark visualization |
| Infra | Docker, Docker Compose (local dev), Cloud Run (both services + a persistent Chroma server), Secret Manager, Cloud Monitoring alerting |
| CI | GitHub Actions — both test suites run on every push/PR |

## Key design decisions worth knowing about

**Pull for dev, push for prod.** Local development uses a Pub/Sub pull-worker pattern (simple, no networking complexity, no need to expose your machine to anything). Production uses real push subscriptions hitting authenticated HTTP endpoints — including a from-scratch OIDC-verified webhook on the Django side, since Cloud Run doesn't support long-lived background workers economically.

**RAG-based risk scoring, not opinion-based.** Every risk score is computed by finding the closest matching clause in a real corpus (market-standard templates + real-world contract data) and asking the LLM to assess deviation from that specific baseline — not just "does this seem risky" in the abstract. The corpus itself lives in ChromaDB, backed by a GCS-FUSE-mounted bucket for durability.

**Parallelized, bounded-concurrency risk scoring.** Each clause's Chroma lookup + Gemini call runs concurrently (bounded thread pool), with results reassembled by clause index regardless of completion order — verified with a test that deliberately makes clauses complete out of order.

**Idempotency that survives redelivery.** A job is only marked "processed" on genuine success — a failure (transient or permanent) leaves it eligible for retry via Pub/Sub redelivery or manual admin requeue, rather than silently swallowing retries.

## Local development

```bash
git clone <this-repo>
cd contract-intel
cp env.example.txt .env   # fill in your GCP project details
docker compose up
```

This boots six containers: Postgres, a Pub/Sub emulator, a GCS emulator, Django's web process, Django's event consumer, and the AI worker. Visit `http://127.0.0.1:8000/`.

**Note:** Vertex AI (Gemini) and BigQuery are never emulated — they're real API calls even in local dev, since no local emulator exists for either. This is a deliberate tradeoff (both have generous free tiers) rather than an oversight.

Seed the RAG corpus once (only needed the first time, or after clearing ChromaDB):
```bash
uv run --project ai_service python infra/seed_corpus.py
uv run --project ai_service python infra/embed_and_load.py
```

## Running tests

```bash
cd ai_service && uv run pytest tests/ -v
cd django_app && uv run python manage.py test analytics documents -v 2
```

Both suites also run automatically on every push/PR via GitHub Actions (`.github/workflows/tests.yml`).

## Deployment

Deployed on Cloud Run: `django-web`, `ai-service`, and `chroma-server` (the persistent RAG corpus, GCS-FUSE-backed). See `PHASE-10-GUIDE.md` and `PHASE-11-GUIDE.md` (in this repo's history) for the full deployment walkthrough, including Cloud SQL setup, Secret Manager, real Pub/Sub push subscriptions, and Cloud Monitoring alerting on the dead-letter queues.

## Known limitations

Tracked honestly in [`BACKLOG.md`](./BACKLOG.md) — including two genuinely open items (a coverage gap in the population-comparison corpus, and a note on the corpus bucket's durability model) rather than a project that claims to have no rough edges. Several real production bugs were found and fixed during deployment (documented in detail there), including a subtle Cloud Run CPU-throttling issue that silently hung background processing with no errors — a good example of the kind of platform-level behavior that's easy to misdiagnose as an application bug.
