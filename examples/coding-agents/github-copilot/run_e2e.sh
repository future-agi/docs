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
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
command -v copilot >/dev/null || { echo "copilot CLI not found on PATH" >&2; exit 1; }

export OTEL_EXPORTER_OTLP_ENDPOINT="${FI_OTLP_BASE:-https://api.futureagi.com/tracer}"
export OTEL_EXPORTER_OTLP_HEADERS="X-Api-Key=${FI_API_KEY},X-Secret-Key=${FI_SECRET_KEY}"
export OTEL_RESOURCE_ATTRIBUTES="project_name=${FI_PROJECT_NAME:-my-copilot-sessions},project_type=observe"
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
copilot -p "$marker: list the files in this folder and read README.md, then reply with one short sentence." \
  --allow-all-tools --no-color
echo
echo "Open project '${FI_PROJECT_NAME:-my-copilot-sessions}' in Future AGI Observe. Expect one trace:"
echo "invoke_agent -> chat + execute_tool spans, all sharing gen_ai.conversation.id."
