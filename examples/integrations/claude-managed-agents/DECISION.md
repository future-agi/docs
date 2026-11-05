# TH-8267 Claude Managed Agents: decision record

Date: 2026-10-20. Status: draft collector recipe; publication blocked until a real deployed-session acceptance run.

## Decision
Nikhil's rule was to ship "not supported" only if nobody else supports it. Since 2026-10-14 Anthropic exports
OpenTelemetry traces for Managed Agents to a Console telemetry destination, and Langfuse, LangSmith, Arize, MLflow and
New Relic document it. So the page is now an integration: destination -> OpenTelemetry Collector -> Future AGI.

## Why a collector
- Anthropic gzips the first request of each delivery. A 2026-10 local self-hosted receiver rejected gzip;
  that does not establish the hosted endpoint's current behavior. The collector accepts gzip and forwards plain OTLP
  to avoid relying on an unqualified downstream compression path.
- A destination sets request headers only; Future AGI needs a `project_name` resource attribute. The collector stamps it.

## Not proven
No real destination, delivery or session was used. Payloads are built from Anthropic's span reference (read 2026-10-20).
Live run blocked on: an Anthropic Console org admin, plus an API key with Managed Agents access and billing.
