#!/usr/bin/env bash
# One real Hermes Agent turn, traced to Future AGI by the traceAI-hermes-agent plugin.
#
#   FI_API_KEY=... FI_SECRET_KEY=... \
#   MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1 MODEL_API_KEY=... MODEL_ID=... \
#   ./run_e2e.sh
#
# Optional: FI_BASE_URL (default https://api.futureagi.com), FI_PROJECT_NAME
# (default hermes-agent), HERMES_REF (Hermes Agent git tag, default v2026.9.24),
# PLUGIN_SPEC (what to pip-install, default traceAI-hermes-agent from PyPI;
# until that is released, a path to a traceAI checkout's
# python/frameworks/hermes-agent), CAPTURE_CONTENT=1 for the content opt-in.
# Needs git and uv. The keys file is deleted when the script exits.
#
# Everything lives in a temporary directory: a Hermes Agent source checkout and
# virtualenv, and HERMES_HOME. Your own ~/.hermes, its profiles and any running
# Hermes gateway are not read or touched. The prompt asks for a directory
# listing and a file read, so the turn has tool calls. The printed marker is
# only in the prompt: with the default config it must not appear in Future AGI.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
: "${MODEL_BASE_URL:?set MODEL_BASE_URL}" "${MODEL_API_KEY:?set MODEL_API_KEY}" "${MODEL_ID:?set MODEL_ID}"
HERMES_REF="${HERMES_REF:-v2026.9.24}"
PLUGIN_SPEC="${PLUGIN_SPEC:-traceAI-hermes-agent}"

WORK="$(mktemp -d)"
git clone -q --depth 1 --branch "$HERMES_REF" https://github.com/NousResearch/hermes-agent "$WORK/hermes-agent"
uv venv -q --python 3.12 "$WORK/venv"
uv pip install -q --python "$WORK/venv/bin/python" -e "$WORK/hermes-agent" "$PLUGIN_SPEC"
HERMES="$WORK/venv/bin/hermes"

export HERMES_HOME="$WORK/hermes-home"
# The keys are written to $HERMES_HOME/.env below; remove them however the
# script ends. Hermes' logs stay in $HERMES_HOME for inspection.
trap 'rm -f "$HERMES_HOME/.env"' EXIT
mkdir -p "$HERMES_HOME" "$WORK/project"
cat > "$HERMES_HOME/config.yaml" <<EOF
model:
  provider: custom
  default: $MODEL_ID
  base_url: $MODEL_BASE_URL
  key_env: MODEL_API_KEY
EOF
umask 077
{
  echo "FI_API_KEY=$FI_API_KEY"
  echo "FI_SECRET_KEY=$FI_SECRET_KEY"
  echo "FI_BASE_URL=${FI_BASE_URL:-https://api.futureagi.com}"
  echo "FI_PROJECT_NAME=${FI_PROJECT_NAME:-hermes-agent}"
  echo "MODEL_API_KEY=$MODEL_API_KEY"
  if [ "${CAPTURE_CONTENT:-0}" = "1" ]; then echo "FI_HERMES_CAPTURE_CONTENT=true"; fi
} > "$HERMES_HOME/.env"
umask 022
printf '# Hermes Agent E2E fixture\n\nA throwaway project for the Future AGI recipe.\n' > "$WORK/project/README.md"

HOME="$WORK" "$HERMES" plugins enable futureagi < /dev/null

MARKER="FI-E2E-MARKER-$(date +%s)"
# Only $HERMES_HOME/.env configures the run, as for a Hermes service.
unset FI_API_KEY FI_SECRET_KEY MODEL_API_KEY FI_BASE_URL FI_PROJECT_NAME
cd "$WORK/project"
HOME="$WORK" "$HERMES" chat -Q \
  -q "List the files in this folder and read README.md with your tools. Reply with its first heading. $MARKER" < /dev/null
echo "hermes_home=$HERMES_HOME"
echo "marker=$MARKER"
