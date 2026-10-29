#!/usr/bin/env bash
# End-to-end run of the Novita AI chat-completions recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.12 or 3.13: traceAI-openai needs < 3.14) and installs requirements.txt
#      (set VENV_DIR to reuse an existing environment)
#   2. runs the tests (they use the local stand-in, a recording collector and a refusing
#      CONNECT probe; no Future AGI and no Novita needed)
#   3. runs app.py (chat, stream, tools, error, bad-model) with tracing on to FI_BASE_URL
#   4. PRIVACY=1: runs app.py twice more with a unique marker in the prompts, once with content
#      capture off (FI_HIDE_*) and once with the default, into <project>-private and <project>-optin,
#      and prints the markers so you can search your own Future AGI store for them
#
# Which API it calls
#   default                              the local stand-in in standin/ (NOT Novita)
#   NOVITA_API_KEY + NOVITA_MODEL        the real Novita API (https://api.novita.ai/openai/v1).
#                                        Needs a Novita account, credit and a key; this script never
#                                        creates one, and a real run costs money.
#   NOVITA_BASE_URL=...                  any OpenAI-compatible base URL (for example the other form
#                                        Novita's docs show, https://api.novita.ai/openai, or a local
#                                        proxy running a real model); combine with NOVITA_API_KEY and
#                                        NOVITA_MODEL.
#
# Other knobs: FI_PROJECT_NAME (default novita-ai-e2e), SKIP_TESTS=1, APP_ARGS="--scenario chat",
# NOVITA_TOOLS_MODEL (model for the tools scenario; Novita answers 400 for tools on a model without
# function calling), NOVITA_MAX_TOKENS (default 128; 0 omits max_tokens).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-http://localhost:4318}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-novita-ai-e2e}"

VENV_DIR="${VENV_DIR:-$HERE/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  PY="${PYTHON:-$(command -v python3.13 || command -v python3.12 || true)}"
  [ -n "$PY" ] || { echo "need python3.12 or python3.13 on PATH (or set PYTHON)"; exit 2; }
  "$PY" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt
fi
PYBIN="$VENV_DIR/bin/python"
"$PYBIN" - <<'PY'
import importlib.metadata as m, sys
names = ["traceai-openai", "fi-instrumentation-otel", "openai", "opentelemetry-sdk"]
print("versions: python", sys.version.split()[0], *(f"{n}=={m.version(n)}" for n in names))
PY

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$PYBIN" -m pytest -q
fi

STUB_PID=""
cleanup() { [ -n "$STUB_PID" ] && kill "$STUB_PID" 2>/dev/null || true; }
trap cleanup EXIT

if [ -n "${NOVITA_API_KEY:-}" ]; then
  : "${NOVITA_MODEL:?set NOVITA_MODEL (a model id copied from the Novita Model Hub)}"
  case "${NOVITA_BASE_URL:-}" in
    "") echo "target: REAL Novita, https://api.novita.ai/openai/v1" ;;
    https://api.novita.ai/*) echo "target: REAL Novita, $NOVITA_BASE_URL" ;;
    *) echo "target: custom base URL $NOVITA_BASE_URL (not Novita)" ;;
  esac
else
  PORT="$("$PYBIN" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  "$PYBIN" standin/novita_stub.py --port "$PORT" --api-key e2e-stand-in-key >/dev/null 2>&1 &
  STUB_PID=$!
  for _ in $(seq 1 30); do curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break; sleep 0.2; done
  export NOVITA_BASE_URL="http://127.0.0.1:$PORT/openai/v1" NOVITA_API_KEY=e2e-stand-in-key NOVITA_MODEL="${NOVITA_MODEL:-example-model-id}"
  echo "target: STAND-IN (not Novita) at $NOVITA_BASE_URL"
fi

echo "== app.py -> API, traces -> $FI_BASE_URL project=$FI_PROJECT_NAME"
"$PYBIN" app.py ${APP_ARGS:-} | grep -E '^(RESULT|base_url|trace_id|session_id)'

if [ "${PRIVACY:-0}" = "1" ]; then
  for mode in private optin; do
    MARK="PRIV-$(date +%s)-$RANDOM$RANDOM"
    if [ "$mode" = "private" ]; then
      export FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_LLM_INVOCATION_PARAMETERS=true
    else
      unset FI_HIDE_INPUTS FI_HIDE_OUTPUTS FI_HIDE_LLM_INVOCATION_PARAMETERS
    fi
    echo "== privacy run ($mode), marker $MARK, project ${FI_PROJECT_NAME}-$mode"
    FI_PROJECT_NAME="${FI_PROJECT_NAME}-$mode" "$PYBIN" app.py --prompt "find $MARK" --system "system note $MARK" ${APP_ARGS:-} \
      | grep -E '^(RESULT|trace_id)'
    echo "MARKER_${mode}=$MARK"
  done
fi
