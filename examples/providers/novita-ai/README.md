# Novita AI tracing example

Runnable companion to the docs page `src/pages/docs/integrations/providers/novita-ai.mdx`
(`/docs/integrations/providers/novita-ai`). It traces Novita AI chat completions made with the stock
`openai` Python client and the existing `traceAI-openai` instrumentor. There is no Novita package and
no `traceai-novita`.

Status: verified against the live Novita API on 2026-10-18 (see "Live vendor verification" below). The
tests are hermetic: they use a local stand-in whose statuses, error bodies, routes and streaming usage
copy the live responses.

## Contents

| Path | What it is |
| --- | --- |
| `app.py` | The recipe (about 10 lines of integration) plus scenarios: `chat`, `stream`, `tools`, `error` (wrong key), `bad-model` (unknown model id) |
| `run_e2e.sh` | Creates a venv, runs the tests, runs `app.py` against a collector, optionally runs the privacy comparison |
| `standin/novita_stub.py` | Local STAND-IN shaped like Novita's chat route as the live API answered on 2026-10-18 (`/openai/v1`, `/openai` and `/v3/openai` routes, 401/404 bodies, usage chunk on every stream). Not Novita |
| `standin/connect_probe.py` | Refusing HTTP proxy that records which host the unmodified client dials. Opens no tunnel |
| `tests/` | pytest suite (see below) |
| `requirements.txt` | Pinned versions the example was tested with |

## Run it

Python 3.10 to 3.13 (traceAI-openai 0.1.10 does not support 3.14).

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_BASE_URL=http://localhost:4318        # your Future AGI collector (run_e2e.sh defaults to this)
./run_e2e.sh                                      # tests, then app.py against the stand-in. No Novita needed
PRIVACY=1 ./run_e2e.sh                            # also: content capture off vs default, with a unique marker
```

Against the real Novita API (needs your own account, credit and a key; this costs money, and the script
never creates an account):

```bash
export NOVITA_API_KEY=...                                      # goes to the OpenAI client only
export NOVITA_MODEL=meta-llama/llama-3.1-8b-instruct           # any id from Novita's Model Hub
export NOVITA_TOOLS_MODEL=meta-llama/llama-3.3-70b-instruct    # only if NOVITA_MODEL has no function calling
./run_e2e.sh
```

Novita answers a request with `tools` on a model without function calling with HTTP 400 "model features
function calling not support", so the tools scenario can use its own model (`NOVITA_TOOLS_MODEL`). `GET
https://api.novita.ai/openai/v1/models` lists each model's `features` and price.

Any OpenAI-compatible server can stand in for the target: set `NOVITA_BASE_URL`, `NOVITA_API_KEY` and
`NOVITA_MODEL`. Setting `NOVITA_BASE_URL=https://api.novita.ai/openai` with your own key uses the other
base URL form that Novita's pages show (see the docs page, "Which base URL"); the live API answered on
both. `NOVITA_MAX_TOKENS=0` omits `max_tokens` (Novita's reference lists it as required; the live API
accepted a call without it).

Run a single scenario with `APP_ARGS="--scenario stream"`. `python app.py --help` lists the flags.

## What the tests cover

| File | Covers |
| --- | --- |
| `tests/test_recipe.py` | The recipe URL; trace shape (AGENT, LLM, TOOL, one session); model and usage; `max_tokens` sent and `tools` not repeated on the tool-result request; streaming usage with and without `stream_options`; wrong-key (401) and unknown-model (404) ERROR spans; `NOVITA_TOOLS_MODEL`; provider label `openai`; keys go only where they belong; uncompressed OTLP with `project_name`; an unreachable collector never breaks the request |
| `tests/test_base_url.py` | With the documented URL the unmodified client dials exactly `api.novita.ai:443` (also for the unversioned `/openai` form); each form makes the client request a different path; a trailing slash; the span is identical for Novita's URL forms and Langfuse's `/v3/openai`; an unrouted path is an ERROR span, not a tracing fault; the span records neither host nor path |
| `tests/test_privacy.py` | A unique marker in every prompt, answer, tool argument and tool result: present by default, absent from every exported byte with `FI_HIDE_*`; no local path, user name or host name on successful calls; what the hide flags do not remove |
| `tests/test_page.py` | The Python snippet on the docs page runs as written (with the base URL swapped for the stand-in) and produces the span the page describes; page and app agree on the URL; the page names every URL form, keeps keys out, and has no em dashes |
| `tests/test_stub.py` | The stand-in only claims fields Novita documents, and its error bodies, routes and stream usage match the live API |

```bash
.venv/bin/python -m pytest -q
```

## Live vendor verification (2026-10-18)

`run_e2e.sh` (with `PRIVACY=1`) and the docs page snippet ran against `api.novita.ai` with a real key,
exporting to a self-hosted Future AGI. Models: `meta-llama/llama-3.1-8b-instruct` (chat, stream, errors,
snippet), `meta-llama/llama-3.3-70b-instruct` (tools), `openai/gpt-oss-120b` (one reasoning call). Both
`/openai/v1` and `/openai` were run with every scenario. What the live API showed, and the stand-in now copies:

| Behaviour | Live result |
| --- | --- |
| Routes | 200 on `/openai/v1/chat/completions`, `/openai/chat/completions` and `/v3/openai/chat/completions`; plain-text `404 page not found` on `/chat/completions`, `/v1/chat/completions`, `/openai/v1/v1/chat/completions` |
| Wrong key | 401 `{"code":401,"reason":"FAILED_TO_AUTH","message":"failed to authenticate API key","metadata":{}}` |
| Unknown or missing model | 404 `{"code":404,"reason":"MODEL_NOT_FOUND","message":"model not found","metadata":{"reason":"model: <id> not found"}}` |
| `tools` on a model without function calling | 400 `INVALID_REQUEST_BODY` "model features function calling not support" (not modelled by the stand-in) |
| Streaming | a final usage chunk (empty `choices`) with or without `stream_options.include_usage` |
| No `max_tokens` | accepted |
| Reasoning model | `reasoning_content` next to `content`; reasoning tokens inside `completion_tokens` |

| Piece | Real | Stand-in |
| --- | --- | --- |
| `openai` SDK, `traceAI-openai`, `fi-instrumentation-otel`, OTLP export | yes | |
| Future AGI collector | yours | the tests use a recording collector |
| The Novita API | when `NOVITA_API_KEY` is set and `NOVITA_BASE_URL` is unset or an `api.novita.ai` URL | `standin/novita_stub.py` in the tests. Reply text and token counts are made up |
| `api.novita.ai` | the client dials it in `tests/test_base_url.py` | a refusing proxy answers 403; no tunnel opens |

Still unverified: Novita's 403 responses, `separate_reasoning` / `enable_thinking`, other Novita APIs, and
TypeScript.

## Versions

Tested 2026-10-18 on Python 3.13: traceAI-openai 0.1.10, fi-instrumentation-otel 1.1.0, openai 3.35.1 (latest,
live runs and tests) and 1.109.1 (tests), opentelemetry-sdk 1.45.1. The suite also passes with traceAI PR 249
(open) overlaid on openai 3.31.0; the assertions that differ are written to accept both.
