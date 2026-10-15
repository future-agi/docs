#!/usr/bin/env bash
# End-to-end run: one real Pi SDK session, traced into Future AGI.
#
#   FI_API_KEY=... FI_SECRET_KEY=... [FI_BASE_URL=<self-hosted collector>] \
#   PI_PROVIDER=my-gateway PI_MODEL=your-model-id MY_GATEWAY_API_KEY=... \
#   ./run_e2e.sh [workdir]
#
# Creates an isolated Pi agent dir and a throwaway project with a README.md,
# installs the example, and runs one prompt that uses the ls and read tools.
# Pi's models.json comes from $PI_MODELS_JSON, or models.example.json: edit its
# placeholder baseUrl and model id first. The prompt carries a unique marker:
# with the default settings the marker must NOT reach Future AGI; rerun with
# FI_HIDE_INPUTS=false to see it on the run span. Exits non-zero when the model
# call failed or was aborted.
# TRACEAI_PI_PACKAGE may point at a local tarball of @traceai/pi-coding-agent
# (built with `pnpm pack`) until the package is on npm.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-$(mktemp -d)}"
mkdir -p "$WORK" && WORK="$(cd "$WORK" && pwd)"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${PI_PROVIDER:?set PI_PROVIDER}" "${PI_MODEL:?set PI_MODEL}"
export FI_PROJECT_NAME="${FI_PROJECT_NAME:-pi-sdk-e2e}"

mkdir -p "$WORK/app" "$WORK/agent" "$WORK/project"
cp "$HERE/package.json" "$HERE/trace_session.mjs" "$WORK/app/"
cp "${PI_MODELS_JSON:-$HERE/models.example.json}" "$WORK/agent/models.json"
printf '# Throwaway project\n\nCreated by run_e2e.sh.\n' > "$WORK/project/README.md"
PKG=""
if [ -n "${TRACEAI_PI_PACKAGE:-}" ]; then
  PKG="$(cd "$(dirname "$TRACEAI_PI_PACKAGE")" && pwd)/$(basename "$TRACEAI_PI_PACKAGE")"
fi

cd "$WORK/app"
if [ -n "$PKG" ]; then
  npm pkg set "dependencies.@traceai/pi-coding-agent=file:$PKG"
fi
npm install --ignore-scripts --silent

MARKER="PI-SDK-MARKER-$(date +%s)-$$"
status=0
PI_CODING_AGENT_DIR="$WORK/agent" PI_CWD="$WORK/project" \
  node trace_session.mjs "List the files in this folder, then read README.md and give me its title. $MARKER" || status=$?
echo "marker=$MARKER"
echo "project=$FI_PROJECT_NAME"
exit "$status"
