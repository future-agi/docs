#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export FI_OTLP_ENDPOINT="${FI_OTLP_ENDPOINT:-http://127.0.0.1:4318/tracer/v1/traces}"
export FI_API_KEY="${FI_API_KEY:-test-api-key}"
export FI_SECRET_KEY="${FI_SECRET_KEY:-test-secret-key}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-cursor-hook-contract}"

python3 "$ROOT/test_contract.py"
