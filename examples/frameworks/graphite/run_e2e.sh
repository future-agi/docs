#!/usr/bin/env bash
# End-to-end run of the Graphite (grafi) recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.11 to 3.13) and installs requirements.txt
#      (set VENV_DIR to reuse an environment, e.g. one with another grafi version)
#   2. runs the tests (fake model endpoint and a recording collector; no Future AGI needed)
#   3. runs app.py three times against a MODEL ENDPOINT, tracing to FI_BASE_URL:
#        chat, tool-error, model-error     (project $FI_PROJECT_NAME, metadata only)
#      then once with FI_CAPTURE_CONTENT=1  (project $FI_PROJECT_NAME-content)
#      then once with the OpenInference OpenAI instrumentor on (project $FI_PROJECT_NAME-provider)
#
# Which model
#   OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL   any OpenAI-compatible endpoint
#   unset                                             the local stand-in in tests/fake_openai.py
#                                                     (NOT a real model; used for a smoke run)
#
# Other knobs: FI_PROJECT_NAME (default graphite-e2e), SKIP_TESTS=1.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-https://api.futureagi.com}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-graphite-e2e}"

VENV_DIR="${VENV_DIR:-$HERE/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  PY="${PYTHON:-$(command -v python3.13 || command -v python3.12 || command -v python3.11 || true)}"
  [ -n "$PY" ] || { echo "need python3.11, 3.12 or 3.13 on PATH (or set PYTHON)"; exit 2; }
  "$PY" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt
fi
PYBIN="$VENV_DIR/bin/python"
"$PYBIN" - <<'PY'
import importlib.metadata as m, sys
names = ["grafi", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http", "openai"]
print("versions: python", sys.version.split()[0], *(f"{n}=={m.version(n)}" for n in names))
PY

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$PYBIN" -m pytest -q
fi

STUB_PID=""
cleanup() { [ -n "$STUB_PID" ] && kill "$STUB_PID" 2>/dev/null || true; }
trap cleanup EXIT

if [ -z "${OPENAI_API_KEY:-}" ]; then
  PORT="$("$PYBIN" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  "$PYBIN" tests/fake_openai.py --port "$PORT" --api-key e2e-stand-in-key >/dev/null 2>&1 &
  STUB_PID=$!
  sleep 1
  export OPENAI_API_KEY=e2e-stand-in-key OPENAI_BASE_URL="http://127.0.0.1:$PORT/v1" OPENAI_MODEL="${OPENAI_MODEL:-stand-in-model}"
  echo "model: STAND-IN (not a real model) at $OPENAI_BASE_URL"
else
  echo "model: ${OPENAI_MODEL:-gpt-4.1-nano} at ${OPENAI_BASE_URL:-https://api.openai.com/v1}"
fi

# Graphite logs every queue poll at DEBUG through loguru; app.py silences it, errors still show.
echo "== metadata only (default): project=$FI_PROJECT_NAME  traces -> $FI_BASE_URL"
fail=0
for scenario in chat tool-error model-error; do
  "$PYBIN" app.py "$scenario" 2>/dev/null | grep '^RESULT' || true
done
echo "== content opt-in (FI_CAPTURE_CONTENT=1): project=$FI_PROJECT_NAME-content"
FI_PROJECT_NAME="$FI_PROJECT_NAME-content" FI_CAPTURE_CONTENT=1 "$PYBIN" app.py chat 2>/dev/null | grep '^RESULT' || fail=1
echo "== with the OpenInference OpenAI instrumentor (adds model and tokens, and a second LLM span): project=$FI_PROJECT_NAME-provider"
FI_PROJECT_NAME="$FI_PROJECT_NAME-provider" GRAFI_PROVIDER_SPANS=1 "$PYBIN" app.py chat 2>/dev/null | grep '^RESULT' || fail=1
exit $fail
