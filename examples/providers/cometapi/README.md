# CometAPI chat completions tracing example

Runnable companion to the docs page `src/pages/docs/integrations/providers/cometapi.mdx`
(`/docs/integrations/providers/cometapi`). It traces CometAPI chat completions made with the stock
`openai` Python client and the existing `traceAI-openai` instrumentor. There is no CometAPI package and
no `traceai-cometapi`.

Status: chat completions verified live against `https://api.cometapi.com/v1` on 2026-10-17 (chat, streaming with
usage, a tool call, a wrong-key 401). The local stand-in in `standin/` is still a stand-in and is not CometAPI.
See "Live vendor verification" and "What is real and what is a stand-in" below.

Scope: `POST /v1/chat/completions` only. Models that CometAPI says need the Responses API, and image,
video and audio routes, are not covered and not tested.

## Contents

| Path | What it is |
| --- | --- |
| `app.py` | The recipe (about 10 lines of integration) plus scenarios: `chat`, `stream`, `tools`, `error` |
| `run_e2e.sh` | Creates a venv, runs the tests, runs `app.py` against a collector, optionally runs the privacy comparison |
| `standin/cometapi_stub.py` | Local STAND-IN shaped like CometAPI's chat endpoint (`/v1/chat/completions`). Not CometAPI |
| `standin/connect_probe.py` | Refusing HTTP proxy that records which host the unmodified client dials. Opens no tunnel |
| `tests/` | pytest suite (see below) |
| `requirements.txt` | Pinned versions the example was tested with |

## Run it

Python 3.10 to 3.13 (traceAI-openai 0.1.10 does not support 3.14).

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_BASE_URL=http://localhost:4318        # your Future AGI collector (run_e2e.sh defaults to this)
./run_e2e.sh                                      # tests, then app.py against the stand-in. No CometAPI needed
PRIVACY=1 ./run_e2e.sh                            # also: content capture off vs default, with a unique marker
```

Against the real CometAPI API (needs your own account and key; this can cost money, and the script never
creates an account):

```bash
export COMETAPI_KEY=...           # CometAPI key, goes to the OpenAI client only
export COMETAPI_MODEL=...         # a current model ID from CometAPI's Models page
./run_e2e.sh
```

Any OpenAI-compatible server can stand in for the target: set `COMETAPI_BASE_URL`, `COMETAPI_KEY` and
`COMETAPI_MODEL`. When `COMETAPI_BASE_URL` is unset the client uses `https://api.cometapi.com/v1`.

Run a single scenario with `APP_ARGS="--scenario stream"`. `python app.py --help` lists the flags.

## What the tests cover

| File | Covers |
| --- | --- |
| `tests/test_recipe.py` | The documented base URL; trace shape (AGENT, LLM, TOOL, one session); model and usage; streaming usage; error span; provider label `openai`; keys go only where they belong; uncompressed OTLP with `project_name`; an unreachable collector never breaks the request |
| `tests/test_base_url.py` | The unmodified client dials exactly `api.cometapi.com:443` and nothing else; a trailing slash reaches the same path; a base URL without `/v1` is a failed call traced as ERROR |
| `tests/test_privacy.py` | A unique marker in every prompt, answer, tool argument and tool result: present by default, absent from every exported byte with `FI_HIDE_*`; what the hide flags do not remove |
| `tests/test_page.py` | The Python snippet on the docs page runs as written (with the base URL swapped for the stand-in) and produces the span the page describes; the page lists Responses, image, video and audio as not covered; no key and no non-chat client |
| `tests/test_stub.py` | The stand-in only claims fields CometAPI documents |

```bash
.venv/bin/python -m pytest -q
```

These tests are a local conformance check of the recipe. They do not use the shared TH-8103 OTLP harness
(traceAI PR 203, still open when this was written); the recording collector in `tests/conftest.py` does the
same job in-process.

## What is real and what is a stand-in

| Piece | Real | Stand-in |
| --- | --- | --- |
| `openai` SDK, `traceAI-openai`, `fi-instrumentation-otel`, OTLP export | yes | |
| Future AGI collector | yours | the tests use a recording collector |
| The CometAPI API | yes on the 2026-10-17 live run, and whenever you set `COMETAPI_KEY` without `COMETAPI_BASE_URL` | `standin/cometapi_stub.py`, shaped from CometAPI's chat page and error-handling page. Nothing in it was captured from a real CometAPI response |
| The `api.cometapi.com` host | the client dials it in `tests/test_base_url.py` | a refusing proxy answers 403; no tunnel opens |

## Live vendor verification (2026-10-17)

`COMETAPI_KEY=... COMETAPI_MODEL=gpt-4o-mini PRIVACY=1 ./run_e2e.sh` against the real API, traces to a local
Future AGI (project `th8103-rest-cometapi-live`). traceAI-openai 0.1.10, openai 3.31.0, Python 3.13.15.
Trace `def9127f-8cff-4921-bd36-06da0b491dfb`: AGENT with 4 LLM spans, 1 TOOL span, `fi_verify` PASS. Non-streaming
spans carry `gpt-4o-mini-2024-07-18` (the response's `model`) and tokens; the streaming span carries tokens but no
model on 0.1.10; the wrong-key call is an ERROR span (401, `cometapi_error`, `invalid token`). With `FI_HIDE_*`
a unique marker is in no stored row of the project; with defaults it is in 5.

Still not proven live: trailing-slash URL, Responses/image/video/audio routes, reasoning-token usage, cost.
A base URL without `/v1` returned `404` JSON (`Invalid URL (POST /chat/completions)`), not a redirect or HTML.
