"""
Reads infra/corpus_cache/normalized_clauses.json (produced by seed_corpus.py)
and loads it into ChromaDB, embedding with a LOCAL sentence-transformers
model — no API calls, $0 embedding cost, since this runs over the entire
corpus plus every incoming clause at inference time.

Local dev: persists to CHROMA_PATH (on-disk). Production (Phase 10): points
at a persistent Chroma SERVER via CHROMA_HOST instead, since Cloud Run's
filesystem is ephemeral. Both branches share the exact same upsert logic —
only the client construction differs.

Run with (from repo root): uv run --project ai_service python infra/embed_and_load.py
"""
import json
import os
import sys
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

CACHE_DIR = REPO_ROOT / "infra" / "corpus_cache"
CLAUSES_JSON = CACHE_DIR / "normalized_clauses.json"

CHROMA_PATH = os.environ.get("CHROMA_PATH", "./.chroma")
CHROMA_HOST = os.environ.get("CHROMA_HOST", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

COLLECTION_NAME = "clauses"
BATCH_SIZE = 100  # keeps memory/CPU bounded; embedding 6000+ clauses in one
                   # call is wasteful, batching also gives visible progress.


def get_chroma_client() -> chromadb.ClientAPI:
    if CHROMA_HOST:
        host, _, port = CHROMA_HOST.partition(":")
        return chromadb.HttpClient(host=host, port=int(port) if port else 8000, ssl=True)

def main():
    if not CLAUSES_JSON.exists():
        raise SystemExit(f"{CLAUSES_JSON} not found — run infra/seed_corpus.py first.")

    clauses = json.loads(CLAUSES_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(clauses)} normalized clauses from {CLAUSES_JSON}")

    print(f"Loading local embedding model '{EMBEDDING_MODEL}' (first run downloads it)...")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

    client = get_chroma_client()
    # get_or_create so re-running this script is safe; delete_collection
    # first if you ever change the embedding model (see guide 4.x notes).
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

    total = len(clauses)
    for start in range(0, total, BATCH_SIZE):
        batch = clauses[start : start + BATCH_SIZE]
        ids = [f"clause-{start + i}" for i in range(len(batch))]
        documents = [c["clause_text"] for c in batch]
        metadatas = [
            {
                "clause_type": c["clause_type"],
                "source": c["source"],
                "source_type": c["source_type"],
                "doc_type": c["doc_type"],
                "standard_position": c["standard_position"],
            }
            for c in batch
        ]
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  upserted {min(start + BATCH_SIZE, total)}/{total}")

    print(f"\nDone. Collection '{COLLECTION_NAME}' now has {collection.count()} clauses.")


if __name__ == "__main__":
    main()
