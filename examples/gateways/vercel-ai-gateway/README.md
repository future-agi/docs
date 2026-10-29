# Vercel AI Gateway with Future AGI tracing

Runnable companion to the docs page `docs/integrations/gateways/vercel-ai-gateway`: trace OpenAI-SDK calls to the [Vercel AI Gateway](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions) (`https://ai-gateway.vercel.sh/v1`) with the existing `traceAI-openai` instrumentor, plus a drain-shaped fixture that shows why a gateway Trace Drain cannot reach an Observe project today.

The tests never call Vercel: they run against a local stand-in whose status codes, error bodies, routes and stream usage copy the live gateway. `run_e2e.sh` calls the real gateway only when you set `GATEWAY_BASE_URL`. The recipe was run against the live gateway on 2026-10-18; see [What was and was not verified](#what-was-and-was-not-verified).

## Layout

| Path | What it is |
| --- | --- |
| `app.py` | The recipe. `register()` + `OpenAIInstrumentor` + an `OpenAI` client with `base_url="https://ai-gateway.vercel.sh/v1"`, and five scenarios: `chat`, `stream`, `tools`, `error` (wrong key), `bad-model` (unknown model id). |
| `standin/vercel_gateway_stub.py` | Local stand-in for the Chat Completions API. Its status codes, error bodies, routes and stream usage copy the live gateway (2026-10-18); its reply text is made up. Not Vercel. |
| `drain/drain-shaped-trace.otlp.json` | OTLP/JSON trace shaped like an AI Gateway Trace Drain: published attribute names, placeholder values, no prompts. Not a capture. |
| `drain/replay_drain.py` | Replays that fixture to a collector, with or without `project_name`, as JSON or Protobuf. |
| `tests/` | 37 tests: stand-in contract, recipe run as a subprocess against a recording collector, privacy marker scans, drain fixture and replay. No Future AGI stack and no Vercel key needed. |
| `run_e2e.sh` | Tests, then the recipe and the drain replay against a real Future AGI collector. |

## Install

Python 3.12 or 3.13 (`traceAI-openai` 0.1.10 requires Python below 3.14).

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt     # pins the tested versions
```

## Run

Tests only (no network, no keys):

```bash
python -m pytest
```

End to end against a Future AGI collector (self-hosted shown):

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 ./run_e2e.sh
```

`run_e2e.sh` creates `.venv` if there is none, runs the tests, starts the stand-in (unless `GATEWAY_BASE_URL` is set), runs `app.py` (project `vercel-ai-gateway-e2e` unless `FI_PROJECT_NAME` is set) and then replays the drain fixture five ways, checking the status each time:

| Replay | Expected |
| --- | --- |
| JSON, no `project_name` (what a drain sends) | `400 ... have no project_name` |
| Protobuf, no `project_name` | `400` |
| JSON with `project_name` | `200` |
| Protobuf with `project_name` | `200` |
| `Authorization: Bearer` instead of `X-Api-Key` / `X-Secret-Key` | `401` |

Against the real gateway (or another OpenAI-compatible endpoint). `GATEWAY_API_KEY` defaults to `AI_GATEWAY_API_KEY`:

```bash
export AI_GATEWAY_API_KEY=...
GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1 GATEWAY_MODEL=<provider>/<model> \
FI_API_KEY=... FI_SECRET_KEY=... ./run_e2e.sh
```

That makes six small calls: chat, stream, two for the tool round trip, a wrong key (401) and an unknown model (404). The last two fail at the gateway before any model runs. On Vercel's free credit pick a free-tier model; the live run used `google/gemini-2.5-flash-lite` and `openai/gpt-4o-mini`.

## Configure

| Variable | Required | Purpose |
| --- | --- | --- |
| `AI_GATEWAY_API_KEY` | Yes | Vercel AI Gateway key. Goes to the OpenAI client only, as `Authorization: Bearer`. |
| `AI_GATEWAY_MODEL` | Yes | Model id from Vercel's model list (`<provider>/<model>`). Not frozen here. |
| `AI_GATEWAY_BAD_MODEL` | No | Model id for the `bad-model` scenario. Default `does-not-exist/no-such-model`. |
| `AI_GATEWAY_BASE_URL` | No | Overrides `https://ai-gateway.vercel.sh/v1`. For a stand-in only. |
| `FI_API_KEY`, `FI_SECRET_KEY` | For export | Future AGI key pair. Goes to the tracer only, as `X-Api-Key` / `X-Secret-Key`. |
| `FI_BASE_URL` | No | Future AGI collector origin (traces go to `$FI_BASE_URL/tracer/v1/traces`). |
| `FI_PROJECT_NAME` | No | Observe project. Default `vercel-ai-gateway`. |
| `FI_HIDE_INPUTS`, `FI_HIDE_OUTPUTS`, `FI_HIDE_LLM_INVOCATION_PARAMETERS` | No | Set to `true` to keep prompts, answers, tool arguments and results, and request parameters out of the spans. |

## Privacy

`traceAI-openai` captures prompts, answers, tool arguments and tool results by default. The three `FI_HIDE_*` variables above turn that off: a unique marker placed in the system prompt, the user prompt, the answer, the tool arguments and the tool result was absent from every byte the collector received (`tests/test_privacy.py`), and, in a live gateway run on 2026-10-18, absent from all 47 ClickHouse tables and a full Postgres dump of a local Future AGI stack (32 occurrences with the default).

They do not remove: the model id, token counts, `session.id`, tool definitions, or error text (status message and the `exception` event with its stack trace on the wire). A 404 body names the model id sent, and a provider-side error body carries the gateway's routing block (providers tried, their request ids, a client session id). `test_documented_residue_of_the_hide_flags` pins that list so the docs page stays true.

## What was and was not verified

Run on 2026-10-18 with `traceAI-openai` 0.1.10, `fi-instrumentation-otel` 1.1.0, `openai` 3.35.1, `opentelemetry-sdk` 1.45.1, Python 3.13.15, against the live gateway `https://ai-gateway.vercel.sh/v1` and a self-hosted Future AGI stack.

| Verified | How |
| --- | --- |
| Spans land in the `register()` project with the agent, LLM and tool hierarchy, model, provider `openai`, tokens, and an ERROR span for a wrong key (401) and an unknown model (404) | `run_e2e.sh` against the live gateway with `google/gemini-2.5-flash-lite` and with `openai/gpt-4o-mini` |
| The page's Python snippet as written | one live call, one `LLM` span with model and tokens |
| The span's model is the response body's model | live: `gemini-2.5-flash-lite` sent, `google/gemini-2.5-flash-lite` on the span |
| Streamed calls have tokens without `stream_options` | live: the gateway sends `usage` on the finish chunk |
| Gateway routing metadata, generation id and `x-vercel-id` are not on successful spans | scan of every stored row of the live project |
| A provider-side error puts the routing block in the status message, even with content hidden | live: `openai/gpt-4o-mini` with `max_tokens=8` (400) |
| Content hidden by `FI_HIDE_*`, shown by default | live marker scans, see Privacy |
| Gateway key and Future AGI keys never cross | `tests/test_recipe.py`, and a by-value search of the stored rows |
| A dead collector does not fail the request | `tests/test_recipe.py` |
| A drain-shaped batch without `project_name` is rejected, with it accepted; Bearer is 401; gzip got HTTP 400 (a release before v1.56.0; current releases accept gzip) | `drain/replay_drain.py` against the local collector |
| Tests pass on `traceAI-openai` 0.1.10 with `openai` 3.35.1 and 1.109.1, and on the open traceAI pull request 249 | three environments; with pull request 249 a live run also showed the model on streamed and failed spans |

| **Not** verified | Why |
| --- | --- |
| A real Trace Drain (its JSON dialect, compression, retries, cancelled requests) | Needs a Pro or Enterprise team and bills $0.05 per 1,000 traces plus $0.50 per GB |
| `AsyncOpenAI`, the Responses API, the Anthropic-format endpoint, embeddings | Not run |
| `429` (free-tier rate limit), `403`, BYOK credentials, Vercel tag and user headers | Not hit or not run |
| The AI SDK (TypeScript) path to the gateway | Covered by the Vercel AI SDK page, not by this example |
| The hosted `api.futureagi.com` collector | Only a self-hosted stack was used |
