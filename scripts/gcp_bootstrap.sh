#!/usr/bin/env bash
# gcp_bootstrap.sh
# Stands up the entire GCP foundation for the Contract Intelligence platform:
# project -> billing -> APIs -> service accounts -> IAM. Idempotent: re-running
# skips anything that already exists. Nothing here costs money on its own; you
# only pay once you create Cloud SQL / Cloud Run / etc. in later phases.
set -euo pipefail

# ============================================================================
# EDIT THESE THREE VALUES, THEN RUN.  Everything else is derived.
# ----------------------------------------------------------------------------
# PROJECT_ID rules: 6-30 chars, lowercase letters/digits/hyphens, must start
# with a letter, GLOBALLY unique across all of GCP. Add a random suffix.
PROJECT_ID="contract-intel-$(whoami | tr -cd 'a-z0-9' | cut -c1-6)-$RANDOM"
# Find yours with:  gcloud billing accounts list
BILLING_ACCOUNT_ID="017674-10861D-A6D2F6"
# Mumbai — closest region to Pune; supports every service in this stack.
REGION="asia-south1"
# ============================================================================

# Vertex/Gemini model availability is widest in us-central1. Keep inference
# there unless you confirm your chosen Gemini models are live in asia-south1.
VERTEX_LOCATION="us-central1"

DJANGO_SA="django-sa"
AI_SA="ai-worker-sa"
DJANGO_SA_EMAIL="${DJANGO_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
AI_SA_EMAIL="${AI_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

info()  { printf "\033[0;34m==>\033[0m %s\n" "$1"; }
ok()    { printf "\033[0;32m  ok\033[0m %s\n" "$1"; }

if [ "$BILLING_ACCOUNT_ID" = "XXXXXX-XXXXXX-XXXXXX" ]; then
  echo "ERROR: set BILLING_ACCOUNT_ID at the top of this script first."
  echo "       Run 'gcloud billing accounts list' to find it."
  exit 1
fi

# --- 1. Project -------------------------------------------------------------
info "Ensuring project '$PROJECT_ID' exists"
if gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  ok "project already exists"
else
  gcloud projects create "$PROJECT_ID" --name="Contract Intelligence"
  ok "project created"
fi
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud config set compute/region "$REGION" >/dev/null
ok "gcloud default project + region set"

# --- 2. Billing -------------------------------------------------------------
info "Linking billing account"
if gcloud billing projects describe "$PROJECT_ID" \
     --format='value(billingEnabled)' 2>/dev/null | grep -qi true; then
  ok "billing already linked"
else
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID"
  ok "billing linked"
fi

# --- 3. Enable APIs ---------------------------------------------------------
info "Enabling required APIs (this can take a minute)"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"
ok "APIs enabled"

# --- 4. Service accounts ----------------------------------------------------
create_sa () {
  local name="$1" display="$2" email="$3"
  if gcloud iam service-accounts describe "$email" >/dev/null 2>&1; then
    ok "service account $name already exists"
  else
    gcloud iam service-accounts create "$name" --display-name="$display"
    ok "service account $name created"
  fi
}
info "Creating service accounts"
create_sa "$DJANGO_SA" "Django product layer" "$DJANGO_SA_EMAIL"
create_sa "$AI_SA"     "FastAPI AI worker"    "$AI_SA_EMAIL"

# --- 5. IAM role bindings ---------------------------------------------------
bind () {  # bind <sa-email> <role>
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$1" --role="$2" \
    --condition=None --quiet >/dev/null
  ok "bound $2 -> $1"
}
info "Binding roles for django-sa (product layer)"
bind "$DJANGO_SA_EMAIL" "roles/cloudsql.client"
bind "$DJANGO_SA_EMAIL" "roles/storage.objectAdmin"
bind "$DJANGO_SA_EMAIL" "roles/pubsub.publisher"
bind "$DJANGO_SA_EMAIL" "roles/pubsub.subscriber"
bind "$DJANGO_SA_EMAIL" "roles/bigquery.jobUser"
bind "$DJANGO_SA_EMAIL" "roles/bigquery.dataViewer"
bind "$DJANGO_SA_EMAIL" "roles/secretmanager.secretAccessor"
bind "$DJANGO_SA_EMAIL" "roles/logging.logWriter"

info "Binding roles for ai-sa (inference worker)"
bind "$AI_SA_EMAIL" "roles/storage.objectViewer"
bind "$AI_SA_EMAIL" "roles/pubsub.publisher"
bind "$AI_SA_EMAIL" "roles/bigquery.dataEditor"
bind "$AI_SA_EMAIL" "roles/bigquery.jobUser"
bind "$AI_SA_EMAIL" "roles/aiplatform.user"
bind "$AI_SA_EMAIL" "roles/secretmanager.secretAccessor"
bind "$AI_SA_EMAIL" "roles/logging.logWriter"

# --- 6. Emit derived values for your .env -----------------------------------
cat <<EOF

============================================================================
Bootstrap complete. Put these into your .env (copy from .env.example):
----------------------------------------------------------------------------
GCP_PROJECT_ID=$PROJECT_ID
GCP_REGION=$REGION
VERTEX_LOCATION=$VERTEX_LOCATION
DJANGO_SA_EMAIL=$DJANGO_SA_EMAIL
AI_SA_EMAIL=$AI_SA_EMAIL
----------------------------------------------------------------------------
Next:
  1) Local auth for dev:   gcloud auth application-default login
  2) Scaffold the repo:    ./scaffold_repo.sh
============================================================================
EOF
