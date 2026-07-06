# AI microservice image. The CMD below (uvicorn serving the /process push
# endpoint) is the PRODUCTION entrypoint — Phase 10's Cloud Run deployment
# uses a Pub/Sub PUSH subscription hitting this exact endpoint. For local
# dev, docker-compose.yml overrides `command:` to run app.pull_worker
# instead (the pull-based dev flow from Phase 3), since local push delivery
# would require exposing this container to the Pub/Sub emulator's push
# mechanism — exactly the networking complexity Phase 3 deliberately
# avoided. Same image, different command depending on context.
#
# Image size/build-time note: this service's dependencies include
# sentence-transformers (which pulls in PyTorch) and chromadb — expect a
# genuinely large image (multiple GB) and a slower first build than the
# django_app image. That's an accepted cost of the $0-embedding-cost
# decision from Phase 4, not a mistake in this Dockerfile.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Same layer-caching rationale as django_app/Dockerfile — dependencies
# rarely change, application code changes often; ordering the COPY this way
# means most rebuilds only re-run the fast `COPY . .` step, not `uv sync`.
COPY pyproject.toml uv.lock ./
ENV UV_HTTP_TIMEOUT=120
RUN uv sync --frozen --no-dev
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Production entrypoint (Phase 10 / Cloud Run push mode). Local dev
# overrides this to run the pull worker instead — see docker-compose.yml.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
