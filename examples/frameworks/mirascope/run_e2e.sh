#!/usr/bin/env bash
# End-to-end run of the Mirascope recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
#   OPENAI_API_KEY=... OPENAI_BASE_URL=... MIRASCOPE_MODEL=openai/gpt-4o-mini ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.10 to 3.13) and installs requirements.txt
#      (set VENV_DIR to reuse an environment, e.g. one on another Python)
#   2. runs the tests (fake model endpoint and a recording collector; no Future AGI needed)
#   3. runs app.py against a MODEL ENDPOINT, tracing to FI_BASE_URL, one process per scenario:
#        chat, tool, agent, stream, error, trace    (project $FI_PROJECT_NAME, metadata only)
#      and again with FI_CAPTURE_CONTENT=1           (project $FI_PROJECT_NAME-content)
#
# Which model
#   OPENAI_API_KEY / OPENAI_BASE_URL / MIRASCOPE_MODEL   any OpenAI-compatible endpoint
#   unset                                                the local stand-in in tests/fake_openai.py
#                                                        (NOT a real model; used for a smoke run)
#
# Other knobs: FI_PROJECT_NAME (default mirascope-e2e), SKIP_TESTS=1, SCENARIOS="chat tool ...".
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-https://api.futureagi.com}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-mirascope-e2e}"
SCENARIOS="${SCENARIOS:-chat tool agent stream error trace}"

VENV_DIR="${VENV_DIR:-$HERE/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  PY="${PYTHON:-$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)}"
  [ -n "$PY" ] || { echo "need python3.10 to python3.13 on PATH (or set PYTHON)"; exit 2; }
  "$PY" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt
fi
PYBIN="$VENV_DIR/bin/python"
"$PYBIN" - <<'PY'
import importlib.metadata as m, sys
names = ["mirascope", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http", "openai"]
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
  "$PYBIN" tests/fake_openai.py --port "$PORT" >/dev/null 2>&1 &
  STUB_PID=$!
  sleep 1
  export OPENAI_API_KEY=e2e-stand-in-key OPENAI_BASE_URL="http://127.0.0.1:$PORT/v1"
  export MIRASCOPE_MODEL="${MIRASCOPE_MODEL:-openai/stand-in-model:completions}"
  echo "model: STAND-IN (not a real model) at $OPENAI_BASE_URL"
else
  export MIRASCOPE_MODEL="${MIRASCOPE_MODEL:-openai/gpt-4o-mini}"
  echo "model: $MIRASCOPE_MODEL at ${OPENAI_BASE_URL:-https://api.openai.com/v1}"
fi

fail=0
run_scenario() {  # prints the RESULT line; the error scenario is expected to report ok=false
  local out want
  out="$("$PYBIN" app.py "$1" 2>/dev/null | grep '^RESULT' || true)"
  echo "${out:-RESULT missing for $1}"
  if [ "$1" = "error" ]; then want='"ok": false'; else want='"ok": true'; fi
  echo "$out" | grep -q "$want" || fail=1
}
echo "== metadata only (default): project=$FI_PROJECT_NAME  traces -> $FI_BASE_URL"
for scenario in $SCENARIOS; do run_scenario "$scenario"; done
echo "== content opt-in (FI_CAPTURE_CONTENT=1): project=$FI_PROJECT_NAME-content"
export FI_CAPTURE_CONTENT=1 FI_PROJECT_NAME="$FI_PROJECT_NAME-content"
for scenario in $SCENARIOS; do run_scenario "$scenario"; done
exit $fail
