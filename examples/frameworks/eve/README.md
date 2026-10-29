# eve (Vercel) to Future AGI

A minimal [eve](https://eve.dev) agent (npm `eve`, repo `vercel/eve`) with one tool, whose OpenTelemetry traces go to Future AGI. Companion to the docs page `/docs/integrations/frameworks/eve`.

eve already emits OpenTelemetry spans. There is no traceAI package: the recipe is three small files that eve discovers on its own.

| File | What it does |
| --- | --- |
| `agent/instrumentation/otel.ts` | `otel({ resource })`: sets `project_name` and `project_type` on the resource. |
| `agent/instrumentation/futureagi.ts` | `otelIntegration(...)`: the Future AGI destination. Content off unless `FI_CAPTURE_CONTENT=1`. |
| `agent/lib/futureagi.ts` | The exporter (OTLP/HTTP protobuf to `$FI_BASE_URL/tracer/v1/traces` with `X-Api-Key` and `X-Secret-Key`), the scope filter that drops eve's `workflow` spans, and the export policy. |

`agent/agent.ts`, `agent/instructions.md` and `agent/tools/get_weather.ts` are the demo agent. The model is any OpenAI-compatible endpoint (`MODEL_BASE_URL`, `MODEL_API_KEY`, `MODEL_ID`); tracing does not depend on it.

## Run it

Node 24 or later (eve requires it).

```bash
npm install
export FI_API_KEY=... FI_SECRET_KEY=...           # Future AGI keys
export FI_PROJECT_NAME=eve-weather-agent
# export FI_BASE_URL=http://localhost:4318         # self-hosted only; default https://api.futureagi.com
export MODEL_BASE_URL=https://api.openai.com/v1 MODEL_API_KEY=... MODEL_ID=gpt-5.4-mini
npm run dev                                         # eve dev
```

Then ask "What's the weather in Paris?" in the eve TUI, or run the server headless and call it:

```bash
npx eve dev --no-ui --port 2000 &
node scripts/invoke.mjs --url http://127.0.0.1:2000 'Use get_weather for the city "Paris".'
```

The reply arrives; the trace appears in the Future AGI project a second later (eve flushes after every tool call and step).

## Tests

| Command | Needs | What it checks |
| --- | --- | --- |
| `npm test` | nothing | Scope filter, exporter URL and headers on the wire (loopback recorder), export policy, the shipped instrumentation files pushed through eve's own destination wrapper (content off and on), the recorded fixture, and the wire checker. |
| `npm run test:eve` | nothing (about a minute) | Real `eve dev` with these files, a deterministic OpenAI-compatible mock model (`scripts/mock-model.mjs`) and a loopback recorder: trace shape, tokens, tool ERROR, workflow spans dropped, marker absent by default and present with `FI_CAPTURE_CONTENT=1`. |
| `./run_e2e.sh` | Future AGI keys and a real model | Three fresh `eve dev` runs through a recorder that forwards to Future AGI: content off (tool call, tool failure, then Ctrl+C), wrong model key (chat ERROR), and `FI_CAPTURE_CONTENT=1` into `<project>-optin`. Prints 21 PASS/FAIL checks on the bytes sent. |

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 FI_PROJECT_NAME=eve-e2e \
MODEL_BASE_URL=... MODEL_API_KEY=... MODEL_ID=... ./run_e2e.sh
```

## Fixture

`test/fixtures/eve-0.80.0-turns.otlp.json` is one OTLP/JSON export request holding three real eve 0.80.0 turns (tool call, failing tool, failing model call) recorded from `run_e2e.sh` with content capture off. Trace, span, run, response, tool-call and delivery ids and the model id were replaced; nothing else was changed. Replay it into a project without eve or a model:

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=eve-fixture node scripts/replay_fixture.mjs
```

The fixture is in the OTLP/JSON shape the shared OTel GenAI conformance harness posts (lowercase hex ids, integer `kind`, `project_name` on the resource).

## Versions tested

eve 0.80.0 (latest on 2026-10-15) and 0.71.0, `@vercel/otel` 2.1.3, `@opentelemetry/sdk-trace-base` 2.12.0, `ai` 7.0.142, `@ai-sdk/openai-compatible` 3.0.70, Node 26.8.1.
