# GitHub Copilot CLI -> Future AGI traces.
#
# Source this file (for example from ~/.zshrc or ~/.bashrc). It only defines a
# `copilot` shell function and holds no keys. The function sets Copilot's
# exporter variables on the Copilot process alone, so other programs you start
# from the same shell do not export to Future AGI. It also names the key
# variables in --secret-env-vars: Copilot strips them from the environment of
# the shell commands and MCP servers it starts and redacts them from its output.
# Copilot's own exporter still reads them.
#
# FI_API_KEY and FI_SECRET_KEY must be set in the shell that runs `copilot`,
# for example loaded from your password manager for the current terminal.
# Do not write the keys into a shell profile.
#
# Copilot appends /v1/traces to the endpoint. Self-hosted Future AGI: replace
# the URL with your collector's base URL, for example http://localhost:14338.
#
# Content capture is OFF. To opt in for one session, in a trusted environment:
#   OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true copilot
# This recipe covers CLI 1.0.98 only; VS Code export is a separate qualification.

copilot() {
  OTEL_EXPORTER_OTLP_ENDPOINT="https://api.futureagi.com/tracer" \
  OTEL_EXPORTER_OTLP_HEADERS="X-Api-Key=${FI_API_KEY},X-Secret-Key=${FI_SECRET_KEY}" \
  OTEL_RESOURCE_ATTRIBUTES="project_name=my-copilot-sessions,project_type=observe" \
  command copilot --secret-env-vars=FI_API_KEY,FI_SECRET_KEY,OTEL_EXPORTER_OTLP_HEADERS "$@"
}
