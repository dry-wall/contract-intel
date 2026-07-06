"""
The RAG retrieval layer. retrieve_template() is the SOLE entry point Phase
5's risk-scoring tool calls — it queries only the baseline (market-standard)
clauses, filtered by source_type, to find the closest template to compare
an incoming clause against. retrieve_population() is the counterpart used
by Phase 7's benchmarking, querying the population (real-world/CUAD) side
of the same collection instead.

Same collection, same embedding model, split only by the source_type
metadata filter — one corpus serving two different purposes.

Phase 11: removed the Phase 10 diagnostic subprocess probe (it was purely
for isolating a bug that turned out to be Cloud Run CPU throttling, not the
model load itself — keeping it would add a full subprocess spawn to every
cold start for no benefit now that the real fix, --no-cpu-throttling, is in
place). Added real OIDC token refresh: the previous version fetched one
token at client construction and never renewed it, so any ai-service
instance staying warm longer than the token's ~1hr lifetime would start
getting 403s from chroma-server again.
"""
import logging
import os

import chromadb
from chromadb.utils import embedding_functions
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token

from app import config

logger = logging.getLogger(__name__)

COLLECTION_NAME = "clauses"
# Refresh the OIDC token if it's older than this, regardless of whether a
# call has actually failed yet — cheaper and simpler than reacting to a 403
# after the fact, and tokens are cheap to fetch (a local, fast call).
TOKEN_MAX_AGE_SECONDS = 45 * 60  # 45 min, safely under the ~1hr token lifetime

_client: chromadb.ClientAPI | None = None
_collection = None
_token_fetched_at: float = 0.0
_chroma_host: str | None = None
_chroma_port: int | None = None


def _get_client() -> chromadb.ClientAPI:
    """
    Rebuilds the client if the cached OIDC token is stale, so a long-lived
    warm instance keeps working instead of silently 403ing after ~1 hour.
    """
    import time

    global _client, _token_fetched_at, _chroma_host, _chroma_port

    chroma_host_env = os.environ.get("CHROMA_HOST", "")
    token_is_stale = (time.time() - _token_fetched_at) > TOKEN_MAX_AGE_SECONDS

    if _client is not None and not (chroma_host_env and token_is_stale):
        return _client

    if chroma_host_env:
        host, _, port = chroma_host_env.partition(":")
        # chroma-server (Phase 10) is --no-allow-unauthenticated — a plain
        # HttpClient never attaches any identity, so every request would
        # get a 403 from Cloud Run's IAM layer before ChromaDB's own code
        # ever runs. Fetch a real OIDC identity token scoped to this
        # service's URL as the audience, and attach it as a bearer header
        # on every request this client makes.
        audience = f"https://{host}"
        token = fetch_id_token(GoogleAuthRequest(), audience)
        _client = chromadb.HttpClient(
            host=host,
            port=int(port) if port else 8000,
            ssl=True,
            headers={"Authorization": f"Bearer {token}"},
        )
        _token_fetched_at = time.time()
        logger.info("chroma client (re)built with fresh OIDC token")
    else:
        chroma_path = os.environ.get("CHROMA_PATH", "./.chroma")
        path = chroma_path if os.path.isabs(chroma_path) else str(config.REPO_ROOT / chroma_path)
        _client = chromadb.PersistentClient(path=path)

    return _client


def _get_collection():
    global _collection
    embedding_model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    # Re-fetch the client every call (cheap: _get_client() only rebuilds
    # when the token is actually stale) rather than caching the collection
    # object itself, so a token refresh mid-run is picked up transparently.
    _collection = _get_client().get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=embed_fn
    )
    return _collection


def retrieve_template(clause_text: str, clause_type: str | None = None, n_results: int = 1) -> list[dict]:
    """
    Queries the BASELINE (market-standard) clauses only. This is what Phase
    5's risk-scoring tool compares an incoming clause against to measure
    deviation. Returns a list of {template_text, similarity, source,
    clause_type, standard_position}, closest match first.
    """
    where = {"source_type": "baseline"}
    if clause_type:
        where = {"$and": [where, {"clause_type": clause_type}]}

    results = _get_collection().query(
        query_texts=[clause_text], n_results=n_results, where=where
    )
    return _format_results(results)


def retrieve_population(clause_text: str, clause_type: str | None = None, n_results: int = 5) -> list[dict]:
    """
    Queries the POPULATION (real-world CUAD) clauses only. Used by Phase 7's
    benchmarking — "how does this compare to everything we've seen".
    """
    where = {"source_type": "population"}
    if clause_type:
        where = {"$and": [where, {"clause_type": clause_type}]}

    results = _get_collection().query(
        query_texts=[clause_text], n_results=n_results, where=where
    )
    return _format_results(results)


def _format_results(results: dict) -> list[dict]:
    if not results["ids"] or not results["ids"][0]:
        return []
    out = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        out.append(
            {
                "template_text": doc,
                # Chroma returns a distance (lower = closer); convert to a
                # 0-1 similarity score that's more intuitive to consume.
                "similarity": max(0.0, 1.0 - dist),
                "source": meta["source"],
                "clause_type": meta["clause_type"],
                "standard_position": meta["standard_position"],
            }
        )
    return out
