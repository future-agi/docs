#!/usr/bin/env bash
# End-to-end run of the Open Agent Spec recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
#   MODEL_BASE_URL=... MODEL_API_KEY=... MODEL_ID=... ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.10 to 3.13) and installs requirements.txt
#      (set VENV_DIR to reuse an environment)
#   2. runs the tests (model stand-in and a loopback recorder; no keys, no Future AGI)
#   3. runs app.py against the MODEL ENDPOINT, tracing to FI_BASE_URL:
#        chat, async, tool-error, model-error           project $FI_PROJECT_NAME (traceAI default: content captured)
#        the same four with FI_HIDE_INPUTS/OUTPUTS=true  project $FI_PROJECT_NAME-hidden
#      Every question carries a fresh marker; they are written to $E2E_OUT/markers.txt so
#      you can search the stored traces for them.
#   4. RUN_OPENINFERENCE=1 also runs scripts/openinference_variant.py (Arize's
#      instrumentor, installed separately) into $FI_PROJECT_NAME-openinference, masked and
#      unmasked. Comparison only.
#
# Which model
#   MODEL_BASE_URL / MODEL_API_KEY / MODEL_ID   any OpenAI-compatible Chat Completions endpoint
#   unset                                       tests/fake_openai.py (NOT a real model; smoke run)
#
# Other knobs: FI_PROJECT_NAME (default open-agent-spec-e2e), SKIP_TESTS=1, RUN_RECIPE=0 (skip step 3),
#              E2E_OUT (default ./.e2e; markers.txt is appended to).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-https://api.futureagi.com}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-open-agent-spec-e2e}"
E2E_OUT="${E2E_OUT:-$HERE/.e2e}"
mkdir -p "$E2E_OUT"

VENV_DIR="${VENV_DIR:-$HERE/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  PY="${PYTHON:-$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)}"
  [ -n "$PY" ] || { echo "need python3.10 to 3.13 on PATH (or set PYTHON)"; exit 2; }
  "$PY" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt
fi
PYBIN="$VENV_DIR/bin/python"
"$PYBIN" - <<'PY'
import importlib.metadata as m, sys
names = ["pyagentspec", "langgraph", "langchain-core", "langchain-openai", "traceai-langchain",
         "fi-instrumentation-otel", "opentelemetry-sdk"]
print("versions: python", sys.version.split()[0], *(f"{n}=={m.version(n)}" for n in names))
PY

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$PYBIN" -m pytest -q
fi

STUB_PID=""
cleanup() { if [ -n "$STUB_PID" ]; then kill "$STUB_PID" 2>/dev/null || true; fi; }
trap cleanup EXIT
if [ -z "${MODEL_BASE_URL:-}" ]; then
  PORT="$("$PYBIN" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  "$PYBIN" tests/fake_openai.py --port "$PORT" --api-key e2e-stand-in-key >/dev/null 2>&1 &
  STUB_PID=$!
  sleep 1
  export MODEL_BASE_URL="http://127.0.0.1:$PORT/v1" MODEL_API_KEY=e2e-stand-in-key MODEL_ID="${MODEL_ID:-stand-in-model}"
  echo "model: STAND-IN (not a real model) at $MODEL_BASE_URL"
else
  : "${MODEL_API_KEY:?set MODEL_API_KEY}" "${MODEL_ID:?set MODEL_ID}"
  echo "model: $MODEL_ID at $MODEL_BASE_URL"
fi

new_marker() { "$PYBIN" -c 'import secrets; print("MARK-" + secrets.token_hex(6))'; }
question() { echo "What is the weather in the city called $1? Repeat the city name $1 in your answer."; }
touch "$E2E_OUT/markers.txt"

run_phase() {  # run_phase <label> <project> <script> [scenarios...]
  local label="$1" project="$2" script="$3"; shift 3
  for scenario in "$@"; do
    local m; m="$(new_marker)"
    echo "$label $project $scenario $m" >> "$E2E_OUT/markers.txt"
    FI_PROJECT_NAME="$project" "$PYBIN" "$script" "$scenario" "$(question "$m")" 2>"$E2E_OUT/$label-$scenario.err" \
      | grep '^RESULT' | sed "s/^/[$label $scenario] /" || true
  done
}

if [ "${RUN_RECIPE:-1}" = "1" ]; then
  echo "== content captured (traceAI default): project=$FI_PROJECT_NAME  traces -> $FI_BASE_URL"
  run_phase default "$FI_PROJECT_NAME" app.py chat async tool-error model-error
  echo "== content hidden (FI_HIDE_INPUTS/OUTPUTS=true): project=$FI_PROJECT_NAME-hidden"
  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true run_phase hidden "$FI_PROJECT_NAME-hidden" app.py chat async tool-error model-error
fi

if [ "${RUN_OPENINFERENCE:-0}" = "1" ]; then
  echo "== comparison: Arize's Agent Spec instrumentor: project=$FI_PROJECT_NAME-openinference"
  run_phase oi-unmasked "$FI_PROJECT_NAME-openinference" scripts/openinference_variant.py chat tool-error model-error
  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true run_phase oi-masked "$FI_PROJECT_NAME-openinference" scripts/openinference_variant.py chat
fi
echo "markers: $E2E_OUT/markers.txt"
