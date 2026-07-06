#!/usr/bin/env bash
# create_real_gcp_resources.sh
# Creates the REAL GCS bucket and Pub/Sub topics on your actual GCP project —
# NOT the local emulators. Idempotent — safe to re-run.
set -euo pipefail

set -a
source .env
set +a

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env first}"
: "${GCS_BUCKET:?Set GCS_BUCKET in .env first}"

echo "==> Creating GCS bucket gs://${GCS_BUCKET} in ${GCP_REGION}"
if gcloud storage buckets describe "gs://${GCS_BUCKET}" >/dev/null 2>&1; then
  echo "    already exists"
else
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --project="${GCP_PROJECT_ID}" \
    --location="${GCP_REGION}" \
    --uniform-bucket-level-access
  echo "    created"
fi

echo "==> Creating Pub/Sub topics"
for topic in "${PUBSUB_UPLOAD_TOPIC:-document-uploaded}" "${PUBSUB_PROCESSED_TOPIC:-document-processed}"; do
  if gcloud pubsub topics describe "$topic" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    echo "    topic '$topic' already exists"
  else
    gcloud pubsub topics create "$topic" --project="${GCP_PROJECT_ID}"
    echo "    topic '$topic' created"
  fi
done

echo "==> Done. Real GCS bucket and Pub/Sub topics are ready."
