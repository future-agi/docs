#!/usr/bin/env bash
# End-to-end run of the NVIDIA NeMo Agent Toolkit `futureagi` trace exporter against a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... LLM_API_KEY=... ./run_e2e.sh
#
# What it does
#   1. clones the toolkit fork branch with the exporter into ./.work/NeMo-Agent-Toolkit (or uses NAT_SRC),
#      creates a Python 3.12 virtual environment with uv and installs the `opentelemetry` and `profiler` extras
#      and the calculator example, exactly as the docs page tells you to
#   2. runs the exporter's own tests (in-process HTTP and gRPC receivers; no Future AGI needed)
#   3. runs the calculator workflow (react_agent with two tools) four times, each with a unique marker:
#        default content, HTTP    -> project $FI_PROJECT_NAME
#        default content, gRPC    -> project $FI_PROJECT_NAME-grpc
#        FI_HIDE_INPUTS/OUTPUTS   -> project $FI_PROJECT_NAME-hidden (the marker must not be stored)
#        wrong secret key         -> nothing stored; a 401 export error is logged and the workflow still answers
#
# Which model
#   LLM_API_KEY (required), LLM_BASE_URL (default NVIDIA-hosted NIM), LLM_MODEL. Any OpenAI-compatible endpoint
#   works through the toolkit's `nim` client.
#
# Other knobs: FI_BASE_URL / FI_GRPC_URL for a self-hosted Future AGI (gRPC URL with scheme), FI_PROJECT_NAME
# (default nat-e2e), NAT_SRC (existing checkout of the branch), SKIP_TESTS=1.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${LLM_API_KEY:?set LLM_API_KEY}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-nat-e2e}"
command -v uv >/dev/null || { echo "need uv (https://docs.astral.sh/uv/)"; exit 2; }

NAT_SRC="${NAT_SRC:-$HERE/.work/NeMo-Agent-Toolkit}"
if [ ! -d "$NAT_SRC/packages/nvidia_nat_opentelemetry" ]; then
  git lfs version >/dev/null 2>&1 || { echo "need Git LFS (https://git-lfs.com/)"; exit 2; }
  git clone --quiet --branch feat/futureagi-tracing-exporter \
    https://github.com/future-agi/NeMo-Agent-Toolkit.git "$NAT_SRC"
fi
cd "$NAT_SRC"
if [ ! -x .venv/bin/nat ]; then
  uv venv --quiet --python 3.12
  VIRTUAL_ENV="$NAT_SRC/.venv" uv pip install --quiet -e ".[opentelemetry,profiler]"
  VIRTUAL_ENV="$NAT_SRC/.venv" uv pip install --quiet -e examples/observability/simple_calculator_observability/
fi
PY="$NAT_SRC/.venv/bin/python"
NAT="$NAT_SRC/.venv/bin/nat"
"$PY" - <<'PY'
import importlib.metadata as m, sys
names = ["nvidia-nat-core", "nvidia-nat-opentelemetry", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http",
         "opentelemetry-exporter-otlp-proto-grpc", "langgraph"]
print("versions: python", sys.version.split()[0], *(f"{n}=={m.version(n)}" for n in names))
PY
# Read the whole listing (grep -q would end the pipe early and fail it under pipefail).
"$NAT" info components -t tracing 2>/dev/null | grep futureagi >/dev/null || { echo "futureagi exporter not registered"; exit 1; }

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  "$PY" -m pytest -q -p no:cacheprovider packages/nvidia_nat_opentelemetry/tests/observability -k futureagi
fi

CONFIG="$HERE/config-futureagi.yml"
PROMPT="First call the current_datetime tool, then use the calculator multiply tool to multiply 1234 by 5678."
run() {  # run <label> <marker> [VAR=value ...]
  local label=$1 marker=$2; shift 2
  echo "== $label (marker $marker)"
  env "$@" "$NAT" run --config_file "$CONFIG" --input "$PROMPT Repeat this reference code exactly: $marker" \
    > "$HERE/.work/$label.log" 2>&1 || echo "   workflow exited non-zero (see .work/$label.log)"
  grep -A1 "Workflow Result" "$HERE/.work/$label.log" | tail -1 | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-160
  grep -E "Failed to export|UNAUTHENTICATED|No parent span" "$HERE/.work/$label.log" \
    | sed -E 's/^[0-9-]+ [0-9:]+ - //; s/step [0-9a-f-]+/step <id>/' | sort | uniq -c | cut -c1-160 || true
}
mkdir -p "$HERE/.work"
stamp=$(date +%s)
run default-http "NATE2E${stamp}A"
run default-grpc "NATE2E${stamp}B" FI_PROTOCOL=grpc FI_PROJECT_NAME="$FI_PROJECT_NAME-grpc"
run hidden "NATE2E${stamp}C" FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_PROJECT_NAME="$FI_PROJECT_NAME-hidden"
run bad-credentials "NATE2E${stamp}D" FI_SECRET_KEY=wrong-secret FI_PROJECT_NAME="$FI_PROJECT_NAME-bad"
cat <<EOF

Check in Future AGI (Observe -> Tracing):
  $FI_PROJECT_NAME          one trace; input and output contain NATE2E${stamp}A; the LLM span has model and tokens
  $FI_PROJECT_NAME-grpc     the same over gRPC, with NATE2E${stamp}B
  $FI_PROJECT_NAME-hidden   inputs, outputs and nat.metadata are __REDACTED__; NATE2E${stamp}C appears nowhere
  $FI_PROJECT_NAME-bad      no project or trace; the log above shows the 401 / UNAUTHENTICATED export error
"No parent span found" lines are the toolkit's graph-agent limitation described on the docs page.
EOF
