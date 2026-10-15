#!/usr/bin/env bash
# End-to-end check: one real Pi SDK session, traced into a Future AGI collector.
#
#   FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 \
#   PI_PROVIDER=my-gateway PI_MODEL=gpt-6-luna MY_GATEWAY_API_KEY=... \
#   ./run_e2e.sh [workdir]
#
# Creates an isolated Pi agent dir (models.json from $PI_MODELS_JSON, default
# models.example.json) and a throwaway project with a README.md, installs the
# example, and runs one prompt that uses the ls and read tools. The prompt
# carries a unique marker: with the default settings the marker must NOT reach
# Future AGI; rerun with FI_HIDE_INPUTS=false to see it on the run span.
# TRACEAI_PI_PACKAGE may point at a local tarball (absolute path) of
# @traceai/pi-coding-agent, for example one built with `pnpm pack`.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-$(mktemp -d)}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${PI_PROVIDER:?set PI_PROVIDER}" "${PI_MODEL:?set PI_MODEL}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-pi-sdk-e2e}"

mkdir -p "$WORK/app" "$WORK/agent" "$WORK/project"
cp "$HERE/package.json" "$HERE/trace_session.mjs" "$WORK/app/"
cp "${PI_MODELS_JSON:-$HERE/models.example.json}" "$WORK/agent/models.json"
printf '# Throwaway project\n\nCreated by run_e2e.sh.\n' > "$WORK/project/README.md"

cd "$WORK/app"
if [ -n "${TRACEAI_PI_PACKAGE:-}" ]; then
  npm pkg set "dependencies.@traceai/pi-coding-agent=file:$TRACEAI_PI_PACKAGE"
fi
npm install --ignore-scripts --silent

MARKER="PI-SDK-MARKER-$(date +%s)-$$"
PI_CODING_AGENT_DIR="$WORK/agent" PI_CWD="$WORK/project" \
  node trace_session.mjs "List the files in this folder, then read README.md and give me its title. $MARKER"
echo "marker=$MARKER"
echo "project=$FI_PROJECT_NAME"
