# Contract Intelligence Platform

Two-service, event-driven contract analysis on GCP.

- `django_app/` — product layer: auth, document/job models, ops admin (Cloud Run)
- `ai_service/` — FastAPI microservice: LangGraph agent + ChromaDB RAG (Cloud Run)
- `infra/`      — gcloud/Terraform scripts, BigQuery DDL, corpus seed scripts
- `scripts/`    — preflight, bootstrap, scaffold

The two services never call each other synchronously — they communicate over
Pub/Sub. See the phase-by-phase build plan for details.

## Getting started
1. `./scripts/preflight_check.sh`
2. edit + run `./scripts/gcp_bootstrap.sh`
3. `cp .env.example .env` and fill in values
4. `gcloud auth application-default login`
