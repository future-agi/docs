# Vercel AI Gateway with Future AGI tracing

Runnable companion to the docs page `docs/integrations/gateways/vercel-ai-gateway`: trace OpenAI-SDK calls to the [Vercel AI Gateway](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions) (`https://ai-gateway.vercel.sh/v1`) with the existing `traceAI-openai` instrumentor, plus a drain-shaped fixture that shows why a gateway Trace Drain cannot reach an Observe project today.

**Nothing here calls Vercel.** The gateway is replaced by a local stand-in. See [What was and was not verified](#what-was-and-was-not-verified).

## Layout

| Path | What it is |
| --- | --- |
| `app.py` | The recipe. `register()` + `OpenAIInstrumentor` + an `OpenAI` client with `base_url="https://ai-gateway.vercel.sh/v1"`, and four scenarios: `chat`, `stream`, `tools`, `error`. |
| `standin/vercel_gateway_stub.py` | Local stand-in for the documented Chat Completions API (auth, errors, SSE, tool calls). Not Vercel. |
| `drain/drain-shaped-trace.otlp.json` | OTLP/JSON trace shaped like an AI Gateway Trace Drain: published attribute names, placeholder values, no prompts. Not a capture. |
| `drain/replay_drain.py` | Replays that fixture to a collector, with or without `project_name`, as JSON or Protobuf. |
| `tests/` | 34 tests: stand-in contract, recipe run as a subprocess against a recording collector, privacy marker scans, drain fixture and replay. No Future AGI stack needed. |
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

`run_e2e.sh` creates `.venv` if there is none, runs the tests, starts the stand-in, runs `app.py` (project `vercel-ai-gateway-e2e` unless `FI_PROJECT_NAME` is set) and then replays the drain fixture five ways, checking the status each time:

| Replay | Expected |
| --- | --- |
| JSON, no `project_name` (what a drain sends) | `400 ... have no project_name` |
| Protobuf, no `project_name` | `400` |
| JSON with `project_name` | `200` |
| Protobuf with `project_name` | `200` |
| `Authorization: Bearer` instead of `X-Api-Key` / `X-Secret-Key` | `401` |

Against another OpenAI-compatible endpoint, including the real gateway:

```bash
GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1 GATEWAY_API_KEY=... GATEWAY_MODEL=<provider>/<model> \
FI_API_KEY=... FI_SECRET_KEY=... ./run_e2e.sh
```

A live Vercel run needs a Vercel account and an AI Gateway key. Vercel asks for a payment method on the team even to use its free credits, so this example does not create either.

## Configure

| Variable | Required | Purpose |
| --- | --- | --- |
| `AI_GATEWAY_API_KEY` | Yes | Vercel AI Gateway key. Goes to the OpenAI client only, as `Authorization: Bearer`. |
| `AI_GATEWAY_MODEL` | Yes | Model id from Vercel's model list (`<provider>/<model>`). Not frozen here. |
| `AI_GATEWAY_BASE_URL` | No | Overrides `https://ai-gateway.vercel.sh/v1`. For a stand-in only. |
| `FI_API_KEY`, `FI_SECRET_KEY` | For export | Future AGI key pair. Goes to the tracer only, as `X-Api-Key` / `X-Secret-Key`. |
| `FI_BASE_URL` | No | Future AGI collector origin (traces go to `$FI_BASE_URL/tracer/v1/traces`). |
| `FI_PROJECT_NAME` | No | Observe project. Default `vercel-ai-gateway`. |
| `FI_HIDE_INPUTS`, `FI_HIDE_OUTPUTS`, `FI_HIDE_LLM_INVOCATION_PARAMETERS` | No | Set to `true` to keep prompts, answers, tool arguments and results, and request parameters out of the spans. |

## Privacy

`traceAI-openai` captures prompts, answers, tool arguments and tool results by default. The three `FI_HIDE_*` variables above turn that off: a unique marker placed in the system prompt, the user prompt, the answer, the tool arguments and the tool result was absent from every byte the collector received (`tests/test_privacy.py`), and absent from all 47 ClickHouse tables and a full Postgres dump of a local Future AGI stack.

They do not remove: the model id, token counts, `session.id`, tool definitions, or error text (status message and the `exception` event with its stack trace on the wire). `test_documented_residue_of_the_hide_flags` pins that list so the docs page stays true.

## What was and was not verified

Run on 2026-10-15 with `traceAI-openai` 0.1.10, `fi-instrumentation-otel` 1.1.0, `openai` 3.31.0, Python 3.13.15, against a self-hosted Future AGI stack.

| Verified | How |
| --- | --- |
| Spans land in the `register()` project with the agent, LLM and tool hierarchy, model, tokens and an ERROR span for a failed call | `run_e2e.sh` against the stand-in and against a local OpenAI-compatible proxy running a real model |
| Content hidden by `FI_HIDE_*`, shown by default | marker scans, see Privacy |
| Gateway key and Future AGI keys never cross | `tests/test_recipe.py` |
| A dead collector does not fail the request | `tests/test_recipe.py` |
| A drain-shaped batch without `project_name` is rejected, with it accepted; Bearer is 401; gzip is refused | `drain/replay_drain.py` against the local collector |
| Tests pass on `traceAI-openai` 0.1.10 with `openai` 3.31.0 and 1.109.1, and on the open traceAI pull request 249 | three environments |

| **Not** verified | Why |
| --- | --- |
| Any call to the real `ai-gateway.vercel.sh` | Needs a Vercel account and a gateway key |
| What model id the live gateway returns, and so what the span shows | Depends on the real gateway. The span shows the response body's model for non-streaming calls (checked with the stand-in only) |
| Whether the live gateway reports `usage` on streamed calls | Vercel's streaming page does not document `stream_options` |
| A real Trace Drain (its JSON dialect, compression, retries, cancelled requests) | Needs a Pro or Enterprise team and bills $0.05 per 1,000 traces plus $0.50 per GB |
| The hosted `api.futureagi.com` collector | Only a self-hosted stack was used |
| `AsyncOpenAI`, the Responses API, the Anthropic-format endpoint | Not run |

Exactly one human step would close the gap: a Vercel AI Gateway API key (`AI_GATEWAY_API_KEY`) for a team with a payment method on file. With it, `GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1 ./run_e2e.sh` produces the first real hosted-gateway span, and the "stand-in only" notes on the docs page can be checked against it.
