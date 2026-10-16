# CometAPI chat completions tracing example

Runnable companion to the docs page `src/pages/docs/integrations/providers/cometapi.mdx`
(`/docs/integrations/providers/cometapi`). It traces CometAPI chat completions made with the stock
`openai` Python client and the existing `traceAI-openai` instrumentor. There is no CometAPI package and
no `traceai-cometapi`.

Status: alpha. **No CometAPI account was used and no request was ever sent to `api.cometapi.com`.** See
"What is real and what is a stand-in" below.

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
| The CometAPI API | only if you set `COMETAPI_KEY` without `COMETAPI_BASE_URL` | `standin/cometapi_stub.py`, shaped from CometAPI's chat page and error-handling page. Nothing in it was captured from a real CometAPI response |
| The `api.cometapi.com` host | the client dials it in `tests/test_base_url.py` | a refusing proxy answers 403; no tunnel opens |

What a live run is still needed for: the exact `model` value CometAPI returns for a request, the real error
body for a wrong key and for a base URL without `/v1` (CometAPI's own pages disagree about whether that is a
404, a 301 or HTML), whether usage includes reasoning tokens for reasoning models, and whether the real SSE
stream matches the stand-in's.

## Versions

Tested 2026-10-15 on Python 3.13: traceAI-openai 0.1.10, fi-instrumentation-otel 1.1.0, openai 3.31.0 (latest),
1.109.1 and 1.69.0, opentelemetry-sdk 1.45.1. The suite also passes with traceAI PR 249 (open) overlaid; the
assertions that differ between the two are written to accept both.
