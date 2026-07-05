"""
Seeds the ChromaDB "clauses" collection from two real, CC BY 4.0 sources:

  BASELINE  (source_type=baseline) — Common Paper standard-terms agreements,
            github.com/CommonPaper/*. Attorney-drafted, market-standard
            clauses. This is what Phase 5's risk-scoring tool retrieves
            against to measure deviation.

  POPULATION (source_type=population) — CUAD v1, github.com/TheAtticusProject/cuad.
            510 real commercial contracts, 41 clause categories, 13,000+
            expert labels. Used for Phase 7's "how does this compare to
            everything we've seen" benchmarking.

Downloads are cached under infra/corpus_cache/ (git-ignored) so re-running
this script doesn't re-download ~40MB every time. Embedding uses a LOCAL
sentence-transformers model (BGE-small by default) — no API calls, no
per-embedding cost, since this runs over the entire corpus plus every
incoming clause at inference time.

Run with (from repo root):  uv run --project ai_service python infra/seed_corpus.py
"""
import json
import os
import sys
import zipfile
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "infra" / "corpus_cache"
sys.path.insert(0, str(REPO_ROOT / "infra"))

from corpus_parsers.common_paper import parse_clauses as parse_common_paper  # noqa: E402
from corpus_parsers.cuad import parse_cuad  # noqa: E402

COMMON_PAPER_DOCS = {
    "Common Paper Mutual NDA": (
        "https://raw.githubusercontent.com/CommonPaper/Mutual-NDA/main/Mutual-NDA.md",
        "NDA",
    ),
    "Common Paper Cloud Service Agreement": (
        "https://raw.githubusercontent.com/CommonPaper/CSA/main/CSA.md",
        "MSA",
    ),
    "Common Paper Data Processing Agreement": (
        "https://raw.githubusercontent.com/CommonPaper/DPA/main/DPA.md",
        "OTHER",
    ),
    "Common Paper Professional Services Agreement": (
        "https://raw.githubusercontent.com/CommonPaper/PSA/main/psa.md",
        "MSA",
    ),
    "Common Paper Software License Agreement": (
        "https://raw.githubusercontent.com/CommonPaper/Software-License-Agreement/main/Software-License-Agreement.md",
        "OTHER",
    ),
}
CUAD_ZIP_URL = "https://raw.githubusercontent.com/TheAtticusProject/cuad/main/data.zip"


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        print(f"  cached: {dest.name}")
        return dest
    print(f"  downloading: {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def fetch_common_paper_clauses() -> list[dict]:
    print("Fetching Common Paper baseline documents...")
    all_clauses = []
    for name, (url, doc_type) in COMMON_PAPER_DOCS.items():
        dest = CACHE_DIR / f"{name.replace(' ', '_')}.md"
        _download(url, dest)
        text = dest.read_text(encoding="utf-8")
        clauses = parse_common_paper(text, source_name=name)
        for c in clauses:
            c["source_type"] = "baseline"
            c["doc_type"] = doc_type
            c["standard_position"] = "market-standard"
        all_clauses.extend(clauses)
        print(f"  {name}: {len(clauses)} clauses")
    return all_clauses


def fetch_cuad_clauses(max_contracts: int | None) -> list[dict]:
    print("Fetching CUAD population dataset...")
    zip_dest = CACHE_DIR / "cuad_data.zip"
    _download(CUAD_ZIP_URL, zip_dest)

    json_dest = CACHE_DIR / "CUADv1.json"
    if not json_dest.exists():
        with zipfile.ZipFile(zip_dest) as zf:
            with zf.open("CUADv1.json") as src, open(json_dest, "wb") as dst:
                dst.write(src.read())

    clauses = parse_cuad(str(json_dest), max_contracts=max_contracts)
    for c in clauses:
        c["source_type"] = "population"
        c["doc_type"] = "OTHER"  # CUAD doesn't label doc_type per contract
        c["standard_position"] = "real-world"
    print(f"  CUAD: {len(clauses)} clauses ({len(set(c['source'] for c in clauses))} contracts)")
    return clauses


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # CUAD's full 510 contracts -> ~6,400 clauses. Cap via env var for a
    # faster local seed while developing; unset (or set to 0) for the full run.
    max_contracts_env = os.environ.get("CUAD_MAX_CONTRACTS", "")
    max_contracts = int(max_contracts_env) if max_contracts_env else None

    baseline = fetch_common_paper_clauses()
    population = fetch_cuad_clauses(max_contracts=max_contracts)
    all_clauses = baseline + population

    out_path = CACHE_DIR / "normalized_clauses.json"
    out_path.write_text(json.dumps(all_clauses, indent=2), encoding="utf-8")
    print(f"\nWrote {len(all_clauses)} normalized clauses to {out_path}")
    print(f"  baseline (Common Paper):  {len(baseline)}")
    print(f"  population (CUAD):        {len(population)}")

    # Embedding + Chroma upsert is a separate step (embed_and_load.py) so
    # this script can be re-run cheaply without re-downloading or re-parsing.


if __name__ == "__main__":
    main()
