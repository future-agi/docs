# Flue to Future AGI

A minimal [Flue](https://flueframework.com) agent (npm `@flue/runtime`, repo `withastro/flue`) with one tool, whose OpenTelemetry traces go to Future AGI. Companion to the docs page `/docs/integrations/frameworks/flue`.

Flue ships `@flue/opentelemetry`, which turns Flue's runtime events into OpenTelemetry GenAI spans. It never creates an SDK or an exporter, so the recipe is two small files that start your own OpenTelemetry SDK and register Flue's instrumentation. There is no traceAI package.

| File | What it does |
| --- | --- |
| `src/futureagi.ts` | Settings as pure functions of the environment: traces URL, the two auth headers, resource attributes (`project_name`, `project_type`, `service.name`), and the content policy. Content off unless `FI_CAPTURE_CONTENT=1`. |
| `src/telemetry.ts` | Starts `NodeSDK` (OTLP/HTTP protobuf, uncompressed, no resource auto-detection, no metric or log exporters), registers `createOpenTelemetryInstrumentation()` with `instrument()`, and flushes on shutdown. |

`src/app.ts`, `src/agents/weather.ts` and `src/tools/get-weather.ts` are the demo agent. `src/model.ts` is demo-only: with `MODEL_BASE_URL` set it registers any OpenAI-compatible endpoint as the `proxy/<MODEL_ID>` model, so the example runs without a provider-specific key. Without it the agent uses `anthropic/claude-haiku-4-5` with `ANTHROPIC_API_KEY`, as in Flue's own getting-started guide (not run here). Tracing does not depend on the provider.

## Run it

Node 22.19 or later (Flue requires it).

```bash
npm install
export FI_API_KEY=... FI_SECRET_KEY=...           # Future AGI keys
export FI_PROJECT_NAME=flue-weather-agent
# export FI_BASE_URL=http://localhost:4318         # self-hosted only; default https://api.futureagi.com
export MODEL_BASE_URL=https://api.openai.com/v1 MODEL_API_KEY=... MODEL_ID=gpt-5.5   # or ANTHROPIC_API_KEY=... and no MODEL_*

npx flue run src/agents/weather.ts --message 'Use get_weather for the city "Paris".'   # one-shot
npx vite build && node dist/server.mjs                                                  # a server on :3000
node scripts/invoke.mjs --url http://127.0.0.1:3000 'Use get_weather for the city "Paris".'
node scripts/ask.ts 'Use get_weather for the city "Paris".'                             # standalone script
```

Ask for `Atlantis` to make the tool throw. `FI_CAPTURE_CONTENT=1` exports prompts, tool arguments and results, and error messages (never stack traces).

## Tests

| Command | Needs | What it checks |
| --- | --- | --- |
| `npm test` | nothing | Settings and content policy, the telemetry module in a child process against a loopback recorder (URL, headers, uncompressed protobuf, resource), the wire checker (it must fail when the recipe leaks), the recorded fixture, and that the docs page shows these files exactly. |
| `npm run test:flue` | nothing (about a minute) | `run_e2e.sh` against a deterministic OpenAI-compatible mock model and a loopback sink standing in for Future AGI: real `flue run`, built server, standalone script and an unreachable exporter. |
| `./run_e2e.sh` | Future AGI keys and a real model | The same phases against a real Future AGI collector, through a recorder that forwards every request unchanged. Prints 27 PASS/FAIL checks on the bytes sent. |

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 FI_PROJECT_NAME=flue-e2e \
MODEL_BASE_URL=... MODEL_API_KEY=... MODEL_ID=... ./run_e2e.sh
```

`run_e2e.sh` phases, each a fresh process with a fresh random marker in the prompt:

| Phase | What runs | What is checked |
| --- | --- | --- |
| off | `flue run`, content off: a tool call, then a tool failure | One trace, `invoke_agent` root with `chat` and `execute_tool` children, model and tokens, marker absent from every byte sent, no content attribute, no error text, no exception message or stack trace |
| model | `flue run` with a wrong model key | ERROR on the `chat` span, run failed, provider error text not exported |
| on | `FI_CAPTURE_CONTENT=1` into `<project>-optin` | Marker in prompt, tool arguments, result and answer; exception message exported, stack trace not |
| server | `vite build`, `node dist/server.mjs`, SIGTERM right after the message settles | The last run's spans arrived |
| script | `scripts/ask.ts` with `start()` and `init()` | The spans arrived when the event loop drained |
| down | `FI_BASE_URL` points at a closed port | The workflow still completes with exit 0 |

All phases run with `OTEL_BSP_SCHEDULE_DELAY=600000`, so the batch timer cannot deliver anything: only the shutdown flush can. Whatever the mode, the checks also require no host name, user name or local path in any request, no API key in any request body, only the three resource attributes the recipe sets, and only `@flue/opentelemetry` spans.

## Fixture

`test/fixtures/flue-2.3.0-turns.otlp.json` is one OTLP/JSON export request holding three real Flue 2.3.0 runs (tool call, failing tool, failing model call) recorded from `run_e2e.sh` with content off. Trace, span, Flue and provider ids, the model id and the model endpoint were replaced; nothing else was changed (`scripts/make_fixture.mjs` rebuilds it from an evidence directory). Replay it into a project without Flue or a model:

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=flue-fixture node scripts/replay_fixture.mjs
```

The fixture is in the OTLP/JSON shape the shared OTel GenAI conformance harness posts (lowercase hex ids, integer `kind`, `project_name` on the resource).

## Versions tested

Flue 2.3.0 (latest on 2026-10-16: `@flue/runtime`, `@flue/opentelemetry`, `@flue/cli`, `@flue/vite`) with real runs against Future AGI. Flue 2.2.2 with `npm run test:flue` (mock model, loopback sink). `@opentelemetry/sdk-node` and `@opentelemetry/exporter-trace-otlp-proto` 0.223.0, `@opentelemetry/sdk-trace-base` and `@opentelemetry/resources` 2.12.0, `@opentelemetry/api` 1.9.1, Node 26.8.1.
