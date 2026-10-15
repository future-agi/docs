#!/usr/bin/env bash
# One real goose session exported to Future AGI with the recipe's settings.
#
# Needs: a goose CLI with a working provider (`goose configure` done), the
# developer extension enabled, and FI_API_KEY / FI_SECRET_KEY in the env.
# Optional: FI_PROJECT_NAME (default goose-sessions),
#           FI_OTLP_TRACES_ENDPOINT (default https://api.futureagi.com/tracer/v1/traces),
#           FI_CAPTURE_CONTENT=true to turn goose's content export on for this run,
#           GOOSE_BIN (default goose).
#
# Prints the marker string it put in the prompt. With content off, searching
# the trace for that marker in Future AGI finds nothing.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
GOOSE_BIN="${GOOSE_BIN:-goose}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

# shellcheck source=futureagi-otel.env
source "$ROOT/futureagi-otel.env"
if [ -n "${FI_OTLP_TRACES_ENDPOINT:-}" ]; then
  export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="$FI_OTLP_TRACES_ENDPOINT"
fi
if [ "${FI_CAPTURE_CONTENT:-}" = "true" ]; then
  export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
else
  unset OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
fi

PROJ="$(mktemp -d)"
trap 'rm -rf "$PROJ"' EXIT
printf '# Demo project\n\nA throwaway folder for the goose tracing check.\n' > "$PROJ/README.md"
MARKER="GOOSE-MARKER-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"

echo "goose $("$GOOSE_BIN" --version | tr -d ' ')"
echo "project: ${FI_PROJECT_NAME:-goose-sessions}"
echo "content capture: ${OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT:-off}"
echo "marker: $MARKER"
(cd "$PROJ" && "$GOOSE_BIN" run -t "$MARKER List the files in this folder and read README.md, then summarize it in one sentence.")
# goose flushes its batch span exporter when the process exits.
echo "done: open Future AGI > Observe > ${FI_PROJECT_NAME:-goose-sessions} and look for a trace rooted at 'reply'."
