"""
Creates the contract_intel BigQuery dataset and processed_clauses table if
they don't already exist. Safe to re-run.

IMPORTANT -- unlike Pub/Sub and GCS, there is no official local BigQuery
emulator. This script (and everything else in Phase 7) runs against REAL
BigQuery even during local development. That's a deliberate, low-risk
choice: BigQuery's free tier (10GB storage + 1TB queries/month) comfortably
covers dev-scale usage, and there's no equivalent-fidelity emulator to fall
back to the way Phase 2/3 used fake-gcs-server and the Pub/Sub emulator.

Run with (from repo root): uv run --project ai_service python infra/create_bigquery_dataset.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET = os.environ.get("BQ_DATASET", "contract_intel")
LOCATION = os.environ.get("GCP_REGION", "asia-south1")

SCHEMA = [
    bigquery.SchemaField("clause_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("job_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("document_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("organization_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("doc_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("clause_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("clause_text", "STRING"),
    bigquery.SchemaField("risk_score", "FLOAT64"),
    bigquery.SchemaField("risk_category", "STRING"),
    bigquery.SchemaField("template_match_source", "STRING"),
    bigquery.SchemaField("template_similarity", "FLOAT64"),
    bigquery.SchemaField("extracted_at", "TIMESTAMP", mode="REQUIRED"),
]


def main():
    client = bigquery.Client(project=PROJECT_ID)
    dataset_ref = f"{PROJECT_ID}.{DATASET}"

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = LOCATION
    dataset = client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset '{dataset_ref}' ready (location={LOCATION}).")

    table_ref = f"{dataset_ref}.processed_clauses"
    table = bigquery.Table(table_ref, schema=SCHEMA)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="extracted_at"
    )
    table.clustering_fields = ["doc_type", "clause_type"]
    table = client.create_table(table, exists_ok=True)
    print(f"Table '{table_ref}' ready (partitioned by day on extracted_at, clustered by doc_type/clause_type).")


if __name__ == "__main__":
    main()
