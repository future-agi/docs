#!/usr/bin/env bash
# One real goose session exported to Future AGI with the recipe's settings:
# goose -> local OpenTelemetry Collector (otel-collector.yaml) -> Future AGI.
#
# Needs: a goose CLI with a working provider (`goose configure` done), the
# developer extension enabled, otelcol-contrib, and FI_API_KEY / FI_SECRET_KEY
# in the env.
# Optional: FI_PROJECT_NAME (default goose-sessions; a project_name in
#           OTEL_RESOURCE_ATTRIBUTES takes precedence, see the collector config),
#           FI_BASE_URL (default https://api.futureagi.com),
#           FI_CAPTURE_CONTENT=true to turn goose's content export on for this run,
#           GOOSE_BIN (default goose), OTELCOL_BIN (default otelcol-contrib),
#           GOOSE_OTLP_LISTEN (default 127.0.0.1:4318; goose is pointed at the same
#           address, for when 4318 is taken).
#
# Prints the marker string it put in the prompt. With content off, searching
# the trace for that marker in Future AGI finds nothing.
set -euo pipefail

: "${FI_API_KEY:?set FI_API_KEY}"
: "${FI_SECRET_KEY:?set FI_SECRET_KEY}"
GOOSE_BIN="${GOOSE_BIN:-goose}"
OTELCOL_BIN="${OTELCOL_BIN:-otelcol-contrib}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

# shellcheck source=futureagi-otel.env
source "$ROOT/futureagi-otel.env"
if [ -n "${GOOSE_OTLP_LISTEN:-}" ]; then
  export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://$GOOSE_OTLP_LISTEN/v1/traces"
fi
if [ "${FI_CAPTURE_CONTENT:-}" = "true" ]; then
  export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
else
  unset OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
fi

WORK="$(mktemp -d)"
COLLECTOR_PID=""
cleanup() {
  if [ -n "$COLLECTOR_PID" ]; then kill "$COLLECTOR_PID" 2>/dev/null || true; wait "$COLLECTOR_PID" 2>/dev/null || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT

"$OTELCOL_BIN" --config "file:$ROOT/otel-collector.yaml" > "$WORK/collector.log" 2>&1 &
COLLECTOR_PID=$!
for _ in $(seq 1 50); do
  if grep -q "Everything is ready" "$WORK/collector.log"; then break; fi
  if ! kill -0 "$COLLECTOR_PID" 2>/dev/null; then cat "$WORK/collector.log" >&2; exit 1; fi
  sleep 0.2
done

mkdir -p "$WORK/project"
printf '# Demo project\n\nA throwaway folder for the goose tracing check.\n' > "$WORK/project/README.md"
MARKER="GOOSE-MARKER-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"

echo "goose $("$GOOSE_BIN" --version | tr -d ' ')"
echo "project: ${FI_PROJECT_NAME:-goose-sessions} (a project_name in OTEL_RESOURCE_ATTRIBUTES wins: ${OTEL_RESOURCE_ATTRIBUTES:-unset})"
echo "collector: ${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT}"
echo "content capture: ${OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT:-off}"
echo "marker: $MARKER"
(cd "$WORK/project" && "$GOOSE_BIN" run -t "$MARKER List the files in this folder and read README.md, then summarize it in one sentence.")
# goose flushes its batch span exporter when the process exits; stopping the
# collector (in cleanup) flushes its batch to Future AGI.
kill "$COLLECTOR_PID"; wait "$COLLECTOR_PID" 2>/dev/null || true; COLLECTOR_PID=""
if grep -qi "error" "$WORK/collector.log"; then grep -i "error" "$WORK/collector.log" | tail -5 >&2; fi
echo "done: open Future AGI > Observe > ${FI_PROJECT_NAME:-goose-sessions} and look for a trace rooted at 'reply'."
