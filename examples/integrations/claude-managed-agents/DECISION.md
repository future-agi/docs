# TH-8267 Claude Managed Agents: decision record

Date: 2026-10-20. Status: supported through a collector recipe (supersedes the 2026-10-16 "not supported yet" page).

## Decision
Nikhil's rule was to ship "not supported" only if nobody else supports it. Since 2026-10-14 Anthropic exports
OpenTelemetry traces for Managed Agents to a Console telemetry destination, and Langfuse, LangSmith, Arize, MLflow and
New Relic document it. So the page is now an integration: destination -> OpenTelemetry Collector -> Future AGI.

## Why a collector
- Anthropic gzips the first request of each delivery. The OTLP spec says "All server components MUST support" `none`
  and `gzip` (https://opentelemetry.io/docs/specs/otlp, "Protocol Details"), so Future AGI's HTTP receiver rejecting gzip
  with 400 is a platform gap. Anthropic's resend-uncompressed on 400/415 hides it only when `project_name` is also present.
- A destination sets request headers only; Future AGI needs a `project_name` resource attribute. The collector stamps it.

## Not proven
No real destination, delivery or session was used. Payloads are built from Anthropic's span reference (read 2026-10-20).
Live run blocked on: an Anthropic Console org admin, plus an API key with Managed Agents access and billing.
