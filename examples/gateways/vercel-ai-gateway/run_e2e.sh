#!/usr/bin/env bash
# End-to-end run of the Vercel AI Gateway recipe against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.12 or 3.13: traceAI-openai needs < 3.14) and installs requirements.txt
#      (set VENV_DIR to reuse an existing environment)
#   2. runs the tests (they use the local stand-in and a recording collector; no Future AGI needed)
#   3. runs app.py (chat, stream, tools, error) against a GATEWAY, with tracing on to FI_BASE_URL
#   4. replays the drain-shaped fixture three ways: without project_name (a drain's shape, expected
#      to be rejected), with project_name (expected to be accepted), and with a Bearer token (401)
#
# Which gateway
#   default                     the local stand-in in standin/ (NOT Vercel)
#   GATEWAY_BASE_URL=...        any OpenAI-compatible base URL, e.g. https://ai-gateway.vercel.sh/v1
#   GATEWAY_API_KEY, GATEWAY_MODEL   the key and model id for that base URL
# A run against the real Vercel AI Gateway needs a Vercel account and a gateway key; this
# script never creates either.
#
# Other knobs: FI_PROJECT_NAME (default vercel-ai-gateway-e2e), DRAIN_PROJECT_NAME (default
# <FI_PROJECT_NAME>-drain), SKIP_TESTS=1, FI_HIDE_INPUTS / FI_HIDE_OUTPUTS (passed through).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-http://localhost:4318}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-vercel-ai-gateway-e2e}"
DRAIN_PROJECT_NAME="${DRAIN_PROJECT_NAME:-${FI_PROJECT_NAME}-drain}"

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

if [ -n "${GATEWAY_BASE_URL:-}" ]; then
  : "${GATEWAY_API_KEY:?set GATEWAY_API_KEY for GATEWAY_BASE_URL}" "${GATEWAY_MODEL:?set GATEWAY_MODEL}"
  export AI_GATEWAY_BASE_URL="$GATEWAY_BASE_URL" AI_GATEWAY_API_KEY="$GATEWAY_API_KEY" AI_GATEWAY_MODEL="$GATEWAY_MODEL"
  echo "gateway: $GATEWAY_BASE_URL"
else
  PORT="$("$PYBIN" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  "$PYBIN" standin/vercel_gateway_stub.py --port "$PORT" --api-key e2e-stand-in-key >/dev/null 2>&1 &
  STUB_PID=$!
  for _ in $(seq 1 30); do curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break; sleep 0.2; done
  export AI_GATEWAY_BASE_URL="http://127.0.0.1:$PORT/v1" AI_GATEWAY_API_KEY=e2e-stand-in-key AI_GATEWAY_MODEL="${AI_GATEWAY_MODEL:-vendor/example-model}"
  echo "gateway: STAND-IN (not Vercel) at $AI_GATEWAY_BASE_URL"
fi

echo "== client path: app.py -> gateway, traces -> $FI_BASE_URL project=$FI_PROJECT_NAME"
"$PYBIN" app.py ${APP_ARGS:-} | grep -E '^(RESULT|trace_id|session_id)'

echo "== drain path: fixture replay (not a Vercel drain), project=$DRAIN_PROJECT_NAME"
ENDPOINT="${FI_BASE_URL%/}/v1/traces"
fail=0
expect() { # expect <http-status> <label> -- replay args...
  local want="$1" label="$2"; shift 3
  local out status
  out="$("$PYBIN" drain/replay_drain.py --endpoint "$ENDPOINT" "$@" 2>&1 || true)"
  printf '%s\n' "$out" | sed 's/^/    /'
  status="$(printf '%s\n' "$out" | sed -n 's/^HTTP \([0-9]*\).*/\1/p' | head -n 1)"
  if [ "$status" = "$want" ]; then echo "  ok   $label -> $want"; else echo "  FAIL $label: wanted $want, got '${status:-none}'"; fail=1; fi
}
expect 400 "drain shape, JSON, no project_name"       -- --format json
expect 400 "drain shape, protobuf, no project_name"   -- --format protobuf
expect 200 "with project_name, JSON"                  -- --format json --project-name "$DRAIN_PROJECT_NAME" --project-type observe
expect 200 "with project_name, protobuf"              -- --format protobuf --project-name "$DRAIN_PROJECT_NAME" --project-type observe
expect 401 "Bearer token instead of the key headers"  -- --auth bearer --project-name "$DRAIN_PROJECT_NAME"
exit $fail
