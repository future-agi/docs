# Cloudflare Agents tracing with Future AGI (example)

Companion to the docs page `src/pages/docs/integrations/frameworks/cloudflare-agents.mdx`.

A Cloudflare Agents SDK agent (npm `agents`, a plain `Agent` subclass) that answers one HTTP request per turn with
one tool, traced by Workers tracing and the Agents SDK's `wrapAISDK`, exported through a Workers OTLP traces
destination to an OpenTelemetry Collector that forwards to Future AGI.

| File | What it is |
| --- | --- |
| `src/index.ts` | The Worker: `WeatherAgent extends Agent`, `onRequest` runs `generateText` from `wrapAISDK(ai)` with tool `get_weather` (throws for cities containing "atlantis") and a server-side `toolApproval` policy; the fetch handler puts the conversation id on the trace root. |
| `wrangler.jsonc` | Deploy config: Durable Object, `nodejs_compat`, `observability.traces` with destination `future-agi`, `persist: false`. Also used by `wrangler dev`. |
| `otelcol.yaml` | The collector the page tells you to run (bearer auth, drops the destination's pre-flight span and the storage spans, `project_name`, span-type/error/session mapping, content, console output and the caller's location off by default, query strings always off). |
| `standin/destination.mjs` | **STANDIN** for Cloudflare's destination, local verification only. Reads the spans and log lines workerd recorded during `wrangler dev` (Local Explorer API) and POSTs them to the collector as OTLP/HTTP JSON with the bearer header. |
| `tools/check_trace.py` | Checks the stored span tree (output of the stack's `fi_verify.py --json`). |
| `tools/scan_columns.py` | Counts stored rows containing a needle in any column of any Future AGI table that stores the project (self-hosted Docker stack). Prints counts only. |
| `run_e2e.sh` | The end-to-end run (below). |
| `test/` | `node --test` suites: stand-in conversion on a turn recorded from workerd, config rules and page sync, `check_trace.py` shapes, and a collector contract test with the real collector image (Docker) on the workerd turn and on a real Cloudflare export (`test/fixtures/cloudflare-export.json`). |

## Tests

```bash
npm install
npm test        # SKIP_DOCKER=1 skips the collector contract test
```

The collector contract test runs `otelcol.yaml` unchanged (only the exporter swapped for a file exporter) on the
recorded turn plus injected content, an e-mail-shaped instance name, a URL with a query string, an exception event, a
console line attached to a span and a raw status message, in both content modes. It also sends a real export from
Cloudflare's destination (the pre-flight span and one turn, gzip-compressed like Cloudflare sends it; the caller's
location, network, host and names replaced with placeholders) and checks the pre-flight filter, the location and
`url.query` removal, sessions and span types.

## Live vendor verification (2026-10-18)

Deployed for real, not part of `run_e2e.sh`: this Worker on Cloudflare Workers (Workers Paid account, `wrangler deploy`,
`wrangler secret put OPENAI_API_KEY`, OpenAI `gpt-4o-mini`), a real Traces destination (created with the Cloudflare API,
same fields as the dashboard) pointing at `otelcol.yaml` on a public HTTPS endpoint (receiver port set by the platform;
a debug exporter added for the test only, to read Cloudflare's payload), forwarding to `api.futureagi.com`.
Scenarios: a turn with a tool, a turn whose tool throws, two turns on an instance named with an e-mail address,
`STORE_MESSAGES=true STORE_TOOLS=true` with the collector default, and an unknown model id. The traces were read back
from the hosted project (agent/llm/tool/chain types, model, tokens, ERROR spans, no marker, no e-mail). The captured
payloads were replayed through the same `otelcol.yaml` into a self-hosted Future AGI (`fi_verify` and `check_trace.py`
pass; content off: no marker, e-mail, location, ASN, query string or pre-flight span in any stored column; content on:
marker stored, e-mail still replaced).

What the real export added to the collector: the pre-flight filter, `url.query` removal, and removing `geo.*` and
`cloudflare.asn` unless `FI_CAPTURE_CONTENT=true`. `check_trace.py model-error` now accepts the runtime ERROR spans
(`POST` 502, provider `fetch` 404, no message) that a deployed Worker produces and local workerd does not.

## End to end

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:<port>   # self-hosted Future AGI
export OPENAI_API_KEY=... OPENAI_BASE_URL=...                                 # any OpenAI-compatible endpoint
export MODEL=gpt-4o-mini                                                      # a model that endpoint serves
VERIFY=/path/to/fi_verify.py ./run_e2e.sh
```

Real: workerd (`wrangler dev`, local mode) running `src/index.ts`, `agents`, the AI SDK, a real model call per step,
the spans and log lines workerd records, the collector container running `otelcol.yaml`, Future AGI.
STANDIN: Cloudflare's destination (`standin/destination.mjs`). No Cloudflare account, login, deploy or tunnel. The live run
above covers the real destination.

Scenarios, all checked against what Future AGI stored:

1. Happy turn with a tool: root `POST` (chain, with the session) `> ... > POST` (the Agent's invocation) `> invoke_agent`
   (agent, no own token usage) `> chat` (llm, model, tokens) `+ execute_tool` (tool) `> tool_approval` (chain,
   approved); one session per trace; no storage spans.
2. The tool throws: `execute_tool` ERROR with message `Error`.
3. The model call fails (wrong model name): `chat` and `invoke_agent` ERROR with `AI_APICallError`.
4. Collector auth: no token and a wrong token get 401.
5. Content off: unique marker in the question, tool arguments/result, the answer and the tool's error text; Agent
   instance named with an e-mail address. Every stored column scanned for the marker, the e-mail, user name, host
   name, home and working directory, stack frames and all keys: none found.
6. Guard: `STORE_MESSAGES=true STORE_TOOLS=true` in the Worker, collector default. The marker reaches the collector
   and is not stored.
7. Content on (`STORE_MESSAGES=true STORE_TOOLS=true`, `FI_CAPTURE_CONTENT=true`): the marker is stored and the
   Input/Output panes fill; e-mail, user, host, paths, stack frames and keys still absent.
8. No cross-project data: each leg's marker is absent from the other legs' projects.

`scan_columns.py` and `fi_verify.py` read the stack's Postgres and ClickHouse containers (`FI_PG_CONTAINER`,
`FI_CH_CONTAINER`). Evidence goes to `./evidence/` (git-ignored: it can contain prompts).

npm 11 may warn that `workerd`'s install script is not approved; `wrangler dev` worked without approving it in the
tested setup.
