#!/usr/bin/env bash
# End-to-end check: one real `pi` session traced into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=pi-e2e \
#   PI_MODEL=anthropic/claude-sonnet-4-5 ./run_e2e.sh [workdir]
#
# Creates a throwaway project with a README.md, installs the extension into
# its .pi/extensions/ directory, and runs one prompt in print mode that uses
# Pi's tools. --approve trusts the throwaway project for this run only.
#
# By default Pi uses your normal agent directory (logins, models). To test a
# custom OpenAI-compatible endpoint without touching it, set PI_MODELS_JSON to
# a models.json (see models.example.json); the script then uses an isolated
# agent directory under the workdir.
#
# The prompt carries a unique marker. With the default settings the marker
# must NOT reach Future AGI; rerun with FI_CAPTURE_CONTENT=true to see it.
# Set FI_OTLP_ENDPOINT for a self-hosted collector, e.g.
# http://localhost:14338/v1/traces.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-$(mktemp -d)}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${PI_MODEL:?set PI_MODEL, e.g. anthropic/claude-sonnet-4-5}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-pi-e2e}"
command -v pi >/dev/null || { echo "pi not found: npm install -g @earendil-works/pi-coding-agent" >&2; exit 1; }

mkdir -p "$WORK/project/.pi/extensions"
cp "$HERE/futureagi-otlp.ts" "$WORK/project/.pi/extensions/"
printf '# Throwaway project\n\nCreated by run_e2e.sh.\n' > "$WORK/project/README.md"
if [ -n "${PI_MODELS_JSON:-}" ]; then
  mkdir -p "$WORK/agent"
  cp "$PI_MODELS_JSON" "$WORK/agent/models.json"
  export PI_CODING_AGENT_DIR="$WORK/agent"
fi

MARKER="PI-MARKER-$(date +%s)-$$"
cd "$WORK/project"
pi --approve -p --model "$PI_MODEL" \
  "List the files in this folder, then read README.md and tell me its title. $MARKER" < /dev/null
echo "pi=$(pi --version)"
echo "marker=$MARKER"
echo "project=$FI_PROJECT_NAME"
