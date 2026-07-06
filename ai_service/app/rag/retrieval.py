"""
The RAG retrieval layer. retrieve_template() is the SOLE entry point Phase
5's risk-scoring tool calls — it queries only the baseline (market-standard)
clauses, filtered by source_type, to find the closest template to compare
an incoming clause against. retrieve_population() is the counterpart used
by Phase 7's benchmarking, querying the population (real-world/CUAD) side
of the same collection instead.

Same collection, same embedding model, split only by the source_type
metadata filter — one corpus serving two different purposes.
"""
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token
import os
import logging
import chromadb
from chromadb.utils import embedding_functions
import concurrent.futures
from app import config
import multiprocessing

COLLECTION_NAME = "clauses"

_client: chromadb.ClientAPI | None = None
_collection = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is not None:
        return _client

    chroma_host = os.environ.get("CHROMA_HOST", "")
    if chroma_host:
        host, _, port = chroma_host.partition(":")
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
    else:
        chroma_path = os.environ.get("CHROMA_PATH", "./.chroma")
        path = chroma_path if os.path.isabs(chroma_path) else str(config.REPO_ROOT / chroma_path)
        _client = chromadb.PersistentClient(path=path)
    return _client

def _load_embed_fn_in_subprocess(model_name, result_queue):
    from chromadb.utils import embedding_functions
    fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    result_queue.put("done")

def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    embedding_model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    logging.getLogger(__name__).info("loading embedding model %s (subprocess probe)", embedding_model)

    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_load_embed_fn_in_subprocess, args=(embedding_model, q))
    p.start()
    p.join(timeout=30)
    if p.is_alive():
        p.terminate()
        raise RuntimeError("Embedding model load hung even in a fresh subprocess — not a threading/event-loop issue")
    logging.getLogger(__name__).info("subprocess probe: model loads fine standalone, exit_code=%s", p.exitcode)

    # Now build it for real, in-process, same as before
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    logging.getLogger(__name__).info("embedding model loaded (in-process)")
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
