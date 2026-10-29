# Cloudflare Think → Future AGI

Example for [Cloudflare Think tracing](https://docs.futureagi.com/docs/integrations/frameworks/cloudflare-think):
a Think agent with one tool, `wrangler.jsonc` with Workers tracing on, and `otelcol.yaml`, the OpenTelemetry
Collector config that sits between a Workers OTLP destination and Future AGI (sets `project_name`, maps
span types and sessions, keeps payloads out unless you opt in).

| File | What it is |
| --- | --- |
| `src/agent.ts` | The Think agent (`WeatherAgent`), one tool, payload switches off by default |
| `src/index.ts` | Worker entry: `POST /turn?conversation=<id>` runs one turn and tags the root span with the conversation |
| `wrangler.jsonc` | `observability.traces`: enabled, destination `future-agi`, `persist: false` |
| `otelcol.yaml` | The collector config shown on the page |
| `run_e2e.sh` | The end-to-end test (below) |
| `tools/standin_destination.mjs` | **STANDIN** for Cloudflare's destination exporter, test only |
| `tools/check_local_tree.mjs`, `tools/explorer.mjs` | Read and check the spans `wrangler dev` recorded |
| `tools/scan_stored.py` | Privacy proof: counts a marker in every stored column of a self-hosted Future AGI |
| `tools/make_fixture.mjs` | Builds `test/fixtures` from a recorded run |
| `test/` | Unit tests: stand-in conversion and tree checks on recorded Think spans, collector config, page/file drift |
| `test/collector.docker.test.mjs` | The real collector (Docker) on a real Workers destination export recorded 2026-10-18 (`test/fixtures/cloudflare-export-2026-10-18.json`, sanitized): pre-flight span, storage spans, query strings, token totals, content off and on. Skipped without Docker |

## Deploy

Run `npm ci`. The config sets `MODEL=gpt-4o-mini` and `OPENAI_BASE_URL=https://api.openai.com/v1` as Worker vars. Run `npx wrangler secret put OPENAI_API_KEY` and enter your model key at the prompt before `npx wrangler deploy`. Configure the collector and the `future-agi` destination as described on the page first. A shell export does not set a deployed Worker binding. For local development, use a git-ignored `.dev.vars` file for the model key.

## Unit tests (no network)

```bash
npm install
npm test        # the collector test also needs Docker (it is skipped without it)
```

## Live vendor verification (2026-10-18)

The page's path ran once for real, by hand (not scripted here, because it needs a Cloudflare account and a public
HTTPS host): this agent deployed with `wrangler deploy` to a Workers Paid account (`wrangler secret put
OPENAI_API_KEY`, `MODEL=gpt-4o-mini`), a Traces destination created with Cloudflare's API pointing at `otelcol.yaml`
(only the listen port changed) on a public HTTPS host, and Future AGI cloud. Turns: a tool call, a second turn in
the same conversation, a tool that throws, an unknown model id, and the payload switches on. What the real export
showed, and what `otelcol.yaml` now handles because of it:

- Cloudflare sends gzip-compressed OTLP/HTTP JSON, one trace over several requests, 1.5 to 3 minutes after the turn.
- Creating a destination sends a test span `Hello from Cloudflare 👋 (<name>)`: `filter/preflight` drops it.
- The query string is in `url.query` as well as `url.full`: `url.query` is deleted.
- `invoke_agent` repeats its chat spans' token totals, which Future AGI added up twice: they move to `think.turn.*`.

`test/collector.docker.test.mjs` replays that export (sanitized) through the real collector.

## End to end (local, no Cloudflare account)

What is real and what is stood in:

- **Real:** `@cloudflare/think` in the Workers runtime (`wrangler dev`, local `workerd`, no Cloudflare account),
  a real model behind an OpenAI-compatible endpoint, one tool; `otelcol.yaml` in
  `otel/opentelemetry-collector-contrib:0.162.0` (Docker); Future AGI.
- **STANDIN:** Cloudflare's OTLP destination. `wrangler dev` records traces in its Local Explorer but has no
  destinations, so `tools/standin_destination.mjs` reads those spans and posts them to the collector as
  OTLP/HTTP JSON with `Authorization: Bearer <token>`, the way a destination is configured on the page.

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_TRACES_URL=http://host.docker.internal:<port>/v1/traces   # as the collector container sees Future AGI
export OPENAI_BASE_URL=... OPENAI_API_KEY=... MODEL=...             # any OpenAI-compatible endpoint
export FI_PROJECT_NAME=think-weather-e2e
SCAN=1 ./run_e2e.sh      # SCAN=1 needs docker access to the Future AGI Postgres and ClickHouse containers
```

Three legs, one project each:

1. `$FI_PROJECT_NAME`: payloads off (Think default), collector default. A turn with a tool call, a turn whose
   tool throws, a turn whose model call fails. Checks the `invoke_agent > chat + execute_tool` tree locally,
   then that the marker is in no stored column.
2. `$FI_PROJECT_NAME-guard`: `storeMessages`/`storeTools` on, collector default. Cloudflare records the
   payloads; none may be stored in Future AGI.
3. `$FI_PROJECT_NAME-optin`: both on and `FI_CAPTURE_CONTENT=true`. The payloads must be stored.

`VERIFY_CMD` (optional) runs after each leg with the project name appended, for a trace-read check.
Evidence (wire bodies, recorded rows, scan counts, logs) goes to `./evidence/`, which is git-ignored.
