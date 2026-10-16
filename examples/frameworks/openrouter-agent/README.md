# OpenRouter Agent tracing with Future AGI

Runnable example for the docs page `src/pages/docs/integrations/frameworks/openrouter-agent.mdx`
(TH-8266). It traces [`@openrouter/agent`](https://www.npmjs.com/package/@openrouter/agent) 0.11.0
`callModel()` runs by turning the package's own lifecycle hooks into OpenTelemetry spans and sending
them to Future AGI. There is no traceAI package for it and nothing wraps `callModel`.

| File | What it is |
| --- | --- |
| `futureagi-tracing.mjs` | `buildTracerProvider()` (OTLP/HTTP, both keys, `project_name`, no gzip) and `createTraceHooks(provider)` (the hooks). Copy this file. |
| `app.mjs` | Demo: `agent` (two model requests and one tool call), `tool-error`, `model-error`. |
| `tests/` | Unit tests with recorded model responses and a recording collector. No keys needed. |
| `tools/responses-shim.mjs` | Only for the end-to-end script when the model sits behind a plain OpenAI-compatible proxy. Not needed with OpenRouter. |
| `run_e2e.sh` | Tests, then the three scenarios against a Future AGI collector, metadata only and with content opt-in. |

```bash
export FI_API_KEY=... FI_SECRET_KEY=...            # Future AGI
export FI_BASE_URL=http://localhost:4318           # self-hosted only; default https://api.futureagi.com
export OPENROUTER_API_KEY=sk-or-...
MODEL=openai/gpt-4o-mini ./run_e2e.sh
```

Unit tests only: `npm ci && npm test` (Node 22 and 26 tested).
