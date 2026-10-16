#!/usr/bin/env bash
# End-to-end run of the TypeSafe (Jev) tracing example against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
#
# What it does
#   1. creates ./.venv (Python 3.10 to 3.13) and installs requirements.txt plus traceAI-typesafe
#      (TRACEAI_TYPESAFE: a pip requirement; set VENV_DIR to reuse an existing environment)
#   2. runs the tests (local stand-in and a recording collector; no Future AGI, no TypeSafe)
#   3. runs app.py: scenario ok (sync + async decisions, models.list), then the failure
#      scenarios fail-422, fail-auth and fail-asset, tracing to FI_BASE_URL
#   4. PRIVACY=1: runs ok, fail-422 and fail-asset again with a unique RUN_MARKER, once with the
#      hide flags on (FI_HIDE_INPUTS/FI_HIDE_OUTPUTS=true) into <project>-hidden and once with the
#      default into <project>-default, and prints the markers so you can search your store
#   5. REAL_AUTH_PROBE=1: one fail-auth call to the real https://api.typesafe.ai with a
#      deliberately invalid key (no account needed, nothing is billed)
#
# Which API it calls
#   default                                the local stand-in in standin/ (NOT TypeSafe)
#   TYPESAFE_API_KEY (TYPESAFE_BASE_URL unset)  the real TypeSafe API, https://api.typesafe.ai.
#                                          Needs your own account and key; a real run is billed.
#   TYPESAFE_API_KEY + TYPESAFE_BASE_URL   any System One host you choose
#
# Other knobs: FI_PROJECT_NAME (default typesafe-e2e), SKIP_TESTS=1, SCENARIOS="ok fail-422".
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
export FI_BASE_URL="${FI_BASE_URL:-http://localhost:4318}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-typesafe-e2e}"
# Until traceAI-typesafe is on PyPI, install it from the traceAI pull request commit.
TRACEAI_TYPESAFE="${TRACEAI_TYPESAFE:-traceAI-typesafe @ git+https://github.com/future-agi/traceAI@e6dd3c0e16e7bd034739fd2537f13a8ec2018b6e#subdirectory=python/frameworks/typesafe}"

VENV_DIR="${VENV_DIR:-$HERE/.venv}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  PY="${PYTHON:-$(command -v python3.12 || command -v python3.13 || command -v python3.11 || command -v python3.10 || true)}"
  [ -n "$PY" ] || { echo "need python3.10 to python3.13 on PATH (or set PYTHON)"; exit 2; }
  "$PY" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt "$TRACEAI_TYPESAFE"
fi
PYBIN="$VENV_DIR/bin/python"
"$PYBIN" - <<'PY'
import importlib.metadata as m, sys
names = ["traceai-typesafe", "typesafe-sdk", "fi-instrumentation-otel", "opentelemetry-sdk"]
print("versions: python", sys.version.split()[0], *(f"{n}=={m.version(n)}" for n in names))
PY

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$PYBIN" -m pytest -q
fi

STUB_PID=""
cleanup() { [ -n "$STUB_PID" ] && kill "$STUB_PID" 2>/dev/null || true; }
trap cleanup EXIT

if [ -n "${TYPESAFE_API_KEY:-}" ]; then
  echo "target: ${TYPESAFE_BASE_URL:-REAL TypeSafe, https://api.typesafe.ai}"
else
  PORT="$("$PYBIN" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  "$PYBIN" standin/systemone_stub.py --port "$PORT" >/dev/null 2>&1 &
  STUB_PID=$!
  for _ in $(seq 1 50); do curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break; sleep 0.2; done
  export TYPESAFE_BASE_URL="http://127.0.0.1:$PORT" TYPESAFE_API_KEY="standin-key"
  echo "target: STAND-IN (not TypeSafe) at $TYPESAFE_BASE_URL"
fi

echo "== app.py -> System One, traces -> $FI_BASE_URL project=$FI_PROJECT_NAME"
for scenario in ${SCENARIOS:-ok fail-422 fail-auth fail-asset}; do
  "$PYBIN" app.py --scenario "$scenario" | grep -E '^(RESULT|billing|tone|urgency|escalate)'
done

if [ "${PRIVACY:-0}" = "1" ]; then
  for mode in hidden default; do
    MARK="TSPRIV-$(date +%s)-$RANDOM$RANDOM"
    echo "== privacy run: mode=$mode marker=$MARK project=$FI_PROJECT_NAME-$mode"
    for scenario in ok fail-422 fail-asset; do
      if [ "$mode" = "hidden" ]; then
        FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true RUN_MARKER="$MARK" FI_PROJECT_NAME="$FI_PROJECT_NAME-$mode" \
          "$PYBIN" app.py --scenario "$scenario" | grep -E '^RESULT scenario'
      else
        RUN_MARKER="$MARK" FI_PROJECT_NAME="$FI_PROJECT_NAME-$mode" "$PYBIN" app.py --scenario "$scenario" | grep -E '^RESULT scenario'
      fi
    done
  done
  echo "Search your Future AGI project <project>-hidden for the hidden marker: it must not appear anywhere."
fi

if [ "${REAL_AUTH_PROBE:-0}" = "1" ]; then
  echo "== real api.typesafe.ai, invalid key (expects HTTP 401)"
  env -u TYPESAFE_BASE_URL "$PYBIN" app.py --scenario fail-auth | grep -E '^RESULT'
fi
