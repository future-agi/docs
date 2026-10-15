#!/usr/bin/env bash
# Run one real GitHub Copilot CLI session that exports its trace to Future AGI.
#
# Needs: `copilot` (npm i -g @github/copilot) signed in, or COPILOT_GITHUB_TOKEN set;
#        FI_API_KEY and FI_SECRET_KEY in the environment.
# Optional: FI_OTLP_BASE (default https://api.futureagi.com/tracer),
#           FI_PROJECT_NAME (default my-copilot-sessions),
#           CAPTURE_CONTENT=1 to opt in to prompt/tool content for this run.
#
# The session runs in a fresh temporary folder, so Copilot only sees two demo files.
# Like the docs page, the exporter variables are set on the copilot command only,
# and the key variables are passed to --secret-env-vars so the shell commands
# Copilot runs here cannot read them.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
command -v copilot >/dev/null || { echo "copilot CLI not found on PATH" >&2; exit 1; }

endpoint="${FI_OTLP_BASE:-https://api.futureagi.com/tracer}"
PROJECT_NAME="${FI_PROJECT_NAME:-my-copilot-sessions}"
[[ "${CAPTURE_CONTENT:-0}" == "1" ]] && PROJECT_NAME="${PROJECT_NAME}-content"
# Inherited settings that would send the trace somewhere else.
unset COPILOT_OTEL_FILE_EXPORTER_PATH COPILOT_OTEL_EXPORTER_TYPE OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
if [[ "${CAPTURE_CONTENT:-0}" == "1" ]]; then
  export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
else
  unset OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
printf '# Demo project\n\nA throwaway folder for the Copilot tracing check.\n' > "$workdir/README.md"
printf 'print("hello")\n' > "$workdir/app.py"

marker="copilot-trace-check-$(date +%s)"
echo "prompt marker: $marker (absent from Future AGI unless CAPTURE_CONTENT=1)"
cd "$workdir"
OTEL_EXPORTER_OTLP_ENDPOINT="$endpoint" \
OTEL_EXPORTER_OTLP_HEADERS="X-Api-Key=${FI_API_KEY},X-Secret-Key=${FI_SECRET_KEY}" \
OTEL_RESOURCE_ATTRIBUTES="project_name=${PROJECT_NAME},project_type=observe" \
  copilot --secret-env-vars=FI_API_KEY,FI_SECRET_KEY,OTEL_EXPORTER_OTLP_HEADERS \
  -p "$marker: list the files in this folder and read README.md, then reply with one short sentence." \
  --allow-all-tools --no-color
echo
echo "Open project '${PROJECT_NAME}' in Future AGI Observe. The first run against a new project may be dropped while Copilot flushes; retry or create the project first. Expect one trace:"
echo "invoke_agent -> chat + execute_tool spans, all sharing gen_ai.conversation.id."
