#!/usr/bin/env bash
# preflight_check.sh
# Verifies every local tool needed for the Contract Intelligence build is present
# and new enough. Exits non-zero if anything is missing so you can't proceed
# with a broken toolchain. Safe to run repeatedly.
set -uo pipefail

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; NC=$'\033[0m'
FAIL=0

pass() { printf "%s  OK  %s %s\n" "$GREEN" "$NC" "$1"; }
warn() { printf "%s WARN %s %s\n" "$YELLOW" "$NC" "$1"; }
fail() { printf "%s FAIL %s %s\n" "$RED" "$NC" "$1"; FAIL=1; }

# --- helper: compare dotted versions, returns 0 if $1 >= $2 -----------------
ver_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }

echo "== Preflight: local toolchain =="

# --- git --------------------------------------------------------------------
if command -v git >/dev/null 2>&1; then
  pass "git $(git --version | awk '{print $3}')"
else
  fail "git not found — install from https://git-scm.com/downloads"
fi

# --- Python 3.12+ -----------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  PYV=$(python3 -c 'import sys; print("%d.%d.%d"%sys.version_info[:3])')
  if ver_ge "$PYV" "3.12.0"; then pass "python $PYV"; else fail "python $PYV found, need >= 3.12.0"; fi
else
  fail "python3 not found — install 3.12+ (pyenv recommended)"
fi

# --- uv (package manager) ---------------------------------------------------
if command -v uv >/dev/null 2>&1; then
  pass "uv $(uv --version | awk '{print $2}')"
else
  fail "uv not found — install:  curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# --- Docker -----------------------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    pass "docker $(docker --version | awk '{print $3}' | tr -d ',') (daemon running)"
  else
    fail "docker installed but daemon not running — start Docker Desktop / the docker service"
  fi
else
  fail "docker not found — install Docker Desktop (Win/Mac) or docker-ce (Linux)"
fi

# --- docker compose v2 ------------------------------------------------------
if docker compose version >/dev/null 2>&1; then
  pass "docker compose $(docker compose version --short 2>/dev/null || echo present)"
else
  fail "'docker compose' (v2 plugin) not found — comes with Docker Desktop; on Linux install docker-compose-plugin"
fi

# --- gcloud CLI -------------------------------------------------------------
if command -v gcloud >/dev/null 2>&1; then
  pass "gcloud $(gcloud version --format='value(\"Google Cloud SDK\")' 2>/dev/null | head -n1)"
  if gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q .; then
    pass "gcloud authenticated as $(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n1)"
  else
    warn "gcloud installed but not authenticated — run: gcloud auth login"
  fi
else
  fail "gcloud not found — install from https://cloud.google.com/sdk/docs/install"
fi

echo "==============================="
if [ "$FAIL" -eq 0 ]; then
  printf "%sAll required tools present. You're clear to run gcp_bootstrap.sh.%s\n" "$GREEN" "$NC"
else
  printf "%sOne or more checks failed. Fix the items above before continuing.%s\n" "$RED" "$NC"
  exit 1
fi
