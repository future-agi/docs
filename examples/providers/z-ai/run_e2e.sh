#!/usr/bin/env bash
# End-to-end run of the Z.ai recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.10 to 3.13: traceAI-openai needs < 3.14) and installs requirements.txt
#      (set VENV_DIR to reuse an existing environment)
#   2. runs the tests (they use the local stand-in, a recording collector and a refusing
#      CONNECT probe; no Future AGI and no Z.ai needed)
#   3. runs app.py (chat, stream, tools, thinking, error) with tracing on to FI_BASE_URL
#   4. PRIVACY=1: runs app.py twice more with a unique marker in the prompts, once with content
#      capture off (FI_HIDE_*) and once with the default, into <project>-private and <project>-optin,
#      and prints the markers so you can search your own Future AGI store for them
#
# Which API it calls
#   default                          the local stand-in in standin/ (NOT Z.ai)
#   ZAI_API_KEY + ZAI_MODEL          the real Z.ai general platform API (https://api.z.ai/api/paas/v4/).
#                                    Needs your own Z.ai account and key; this script never creates one,
#                                    and a call to a paid model costs money.
#   ZAI_BASE_URL=...                 any OpenAI-compatible base URL (for example a local proxy running a
#                                    real model); combine with ZAI_API_KEY and ZAI_MODEL.
#
# Other knobs: FI_PROJECT_NAME (default z-ai-e2e), SKIP_TESTS=1, APP_ARGS="--scenario chat".
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-http://localhost:4318}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-z-ai-e2e}"

VENV_DIR="${VENV_DIR:-$HERE/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  PY="${PYTHON:-$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)}"
  [ -n "$PY" ] || { echo "need Python 3.10 to 3.13 on PATH (or set PYTHON)"; exit 2; }
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

if [ -n "${ZAI_API_KEY:-}" ]; then
  : "${ZAI_MODEL:?set ZAI_MODEL (a current model code from the Z.ai model list)}"
  if [ -n "${ZAI_BASE_URL:-}" ]; then
    echo "target: custom base URL $ZAI_BASE_URL (not necessarily Z.ai)"
  else
    echo "target: REAL Z.ai general platform, https://api.z.ai/api/paas/v4/"
  fi
else
  PORT="$("$PYBIN" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  "$PYBIN" standin/zai_stub.py --port "$PORT" --api-key e2e-stand-in-key >/dev/null 2>&1 &
  STUB_PID=$!
  for _ in $(seq 1 30); do curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break; sleep 0.2; done
  export ZAI_BASE_URL="http://127.0.0.1:$PORT/api/paas/v4/" ZAI_API_KEY=e2e-stand-in-key ZAI_MODEL="${ZAI_MODEL:-glm-example-model}"
  echo "target: STAND-IN (not Z.ai) at $ZAI_BASE_URL"
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
