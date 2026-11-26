# Cloudflare AI Chat tracing with Future AGI (example)

Companion to the docs page `src/pages/docs/integrations/frameworks/cloudflare-ai-chat.mdx`.

A Cloudflare AI Chat agent (`@cloudflare/ai-chat` `AIChatAgent`) with one tool, traced by Workers tracing and the
Agents SDK's `wrapAISDK`, exported through a Workers OTLP traces destination to an OpenTelemetry Collector that
forwards to Future AGI.

| File | What it is |
| --- | --- |
| `src/index.ts` | The Worker: `SupportChat extends AIChatAgent`, `wrapAISDK(ai)`, tool `lookup_order` (throws for ids starting with `FAIL`). |
| `wrangler.jsonc` | Deploy config: Durable Object, `nodejs_compat`, `observability.traces` with destination `future-agi`, `persist: false`. Also used by `wrangler dev`. |
| `otelcol.yaml` | The collector the page tells you to run (bearer auth, storage-span filter, `project_name`, span-type/error/session mapping, content off by default). |
| `standin/destination.mjs` | **STANDIN** for Cloudflare's destination, for running without a Cloudflare account (`run_e2e.sh`). Reads the spans workerd recorded during `wrangler dev` (Local Explorer API) and POSTs them to the collector as OTLP/HTTP JSON with the bearer header. |
| `tools/chat.mjs` | Sends one chat message over the AIChatAgent WebSocket protocol (the frame `useAgentChat` sends). |
| `tools/check_trace.py` | Checks the stored span tree (output of the stack's `fi_verify.py --json`). |
| `tools/scan_columns.py` | Counts stored rows containing a needle in any column of any Future AGI table that stores the project (self-hosted Docker stack). Prints counts only. |
| `run_e2e.sh` | The end-to-end run (below). |
| `test/` | `node --test` suites: stand-in conversion, chat frame, config rules and page-sync, and a collector contract test with the real collector image (Docker). |
| `test/fixtures/cloudflare-export-2026-10-18.json` | Sanitized OTLP export from a real Cloudflare Workers traces destination (deployed Worker, 2026-10-18): the destination's test span, a WebSocket upgrade, a tool-error turn, a model-error turn, a content-on turn, a socket close. Names, e-mail, markers, caller city/region and ASN replaced; at most 2 storage spans per trace. |

## Tests

```bash
npm install
npm test        # SKIP_DOCKER=1 skips the collector contract test
```

The collector contract test runs `otelcol.yaml` unchanged (only the exporter swapped for a file exporter), in both
content modes, on two inputs: a local workerd turn plus injected content, an e-mail-shaped instance name, a URL with a
query string, an exception event and a raw status message; and the real Cloudflare export above (test span dropped,
closed-socket `GET` not ERROR, city/region and `url.query` removed, tool and model errors mapped, content removed unless
`FI_CAPTURE_CONTENT=true`).

## Live vendor verification (2026-10-18)

The page was followed on a real Cloudflare account on Workers Paid: `src/index.ts` and `wrangler.jsonc` deployed with
`wrangler deploy` (names changed only), a Traces destination created with the Cloudflare API, `otelcol.yaml` on Google
Cloud Run (plus a file that only moves the receiver to `$PORT`), forwarding to Future AGI cloud. Turns: a tool call
(twice on one Durable Object), a tool that throws, a wrong model name, and the privacy turns with the Worker switches off
and on. Every turn reached Future AGI cloud with agent/llm/tool types, model, tokens and the expected errors. What the
real export taught (each is now handled in `otelcol.yaml` and covered by the fixture test): each message is its own
trace rooted at `hibernatableWebSocket`; saving a destination sends a `Hello from Cloudflare` test span; the upgrade `GET`
is ERROR (`responseStreamDisconnected`) when the client closes the socket; request spans carry the caller's city and
region. Turns reached the collector 80 to 160 seconds after they ended.

The local end-to-end run below still uses the stand-in, so it needs no account.

## End to end

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:<port>   # self-hosted Future AGI
export OPENAI_API_KEY=... OPENAI_BASE_URL=...                                 # any OpenAI-compatible endpoint
export MODEL=gpt-4o-mini                                                      # a model that endpoint serves
VERIFY=/path/to/fi_verify.py ./run_e2e.sh
```

Real: workerd (`wrangler dev`, local mode) running `src/index.ts`, `@cloudflare/ai-chat`, `agents`, the AI SDK, a real
model call per step, the spans workerd records, the collector container running `otelcol.yaml`, Future AGI.
STANDIN: Cloudflare's destination (`standin/destination.mjs`). No Cloudflare account, login, deploy or tunnel. Locally
the turn is nested in the upgrade request's trace; on a deployed Worker it is its own trace (see the page).

Scenarios, all checked against what Future AGI stored:

1. Happy turn with a tool: `chat_turn > invoke_agent (agent) > chat (llm, model, tokens) + execute_tool (tool)`, a session,
   no storage spans, no token usage on `invoke_agent`.
2. The tool throws: `execute_tool` ERROR with message `Error`.
3. The model call fails (wrong model name): `chat` and `invoke_agent` ERROR with `AI_APICallError` (a deployed Worker
   also marks the provider `fetch` ERROR; `check_trace.py` allows that).
4. Collector auth: no token and a wrong token get 401.
5. Content off: unique marker in prompt, tool arguments/result and error text, agent instance named with an e-mail
   address. Every stored column scanned for the marker, the e-mail, user name, host name, home and working directory,
   stack frames and all keys: none found.
6. Content on (`STORE_MESSAGES=true STORE_TOOLS=true` in the Worker, `FI_CAPTURE_CONTENT=true` on the collector): the
   marker is stored and the Input/Output panes fill; e-mail, user, host, paths, stack frames and keys still absent.

`scan_columns.py` and `fi_verify.py` read the stack's Postgres and ClickHouse containers (`FI_PG_CONTAINER`,
`FI_CH_CONTAINER`). Evidence goes to `./evidence/` (git-ignored: it can contain prompts).

npm 11 may warn that `workerd`'s install script is not approved; `wrangler dev` worked without approving it in the
tested setup.
