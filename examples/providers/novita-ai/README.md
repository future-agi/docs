# Novita AI tracing example

Runnable companion to the docs page `src/pages/docs/integrations/providers/novita-ai.mdx`
(`/docs/integrations/providers/novita-ai`). It traces Novita AI chat completions made with the stock
`openai` Python client and the existing `traceAI-openai` instrumentor. There is no Novita package and
no `traceai-novita`.

Status: alpha. **No Novita account was used and no request was ever sent to `api.novita.ai`.** See
"What is real and what is a stand-in" below.

## Contents

| Path | What it is |
| --- | --- |
| `app.py` | The recipe (about 10 lines of integration) plus scenarios: `chat`, `stream`, `tools`, `error` |
| `run_e2e.sh` | Creates a venv, runs the tests, runs `app.py` against a collector, optionally runs the privacy comparison |
| `standin/novita_stub.py` | Local STAND-IN shaped like Novita's chat route (`/openai/v1/chat/completions`, and `/openai/chat/completions`). Not Novita |
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
export NOVITA_API_KEY=...         # Novita API key, goes to the OpenAI client only
export NOVITA_MODEL=...           # a model id copied from Novita's Model Hub
./run_e2e.sh
```

Any OpenAI-compatible server can stand in for the target: set `NOVITA_BASE_URL`, `NOVITA_API_KEY` and
`NOVITA_MODEL`. Setting `NOVITA_BASE_URL=https://api.novita.ai/openai` with your own key tries the other
base URL form that Novita's pages show (see the docs page, "Which base URL"). `NOVITA_MAX_TOKENS=0` omits
`max_tokens` for a stand-in whose model rejects it; Novita's reference lists the field as required.

Run a single scenario with `APP_ARGS="--scenario stream"`. `python app.py --help` lists the flags.

## What the tests cover

| File | Covers |
| --- | --- |
| `tests/test_recipe.py` | The recipe URL; trace shape (AGENT, LLM, TOOL, one session); model and usage; `max_tokens` sent and `tools` not repeated on the tool-result request; streaming usage; error span; provider label `openai`; keys go only where they belong; uncompressed OTLP with `project_name`; an unreachable collector never breaks the request |
| `tests/test_base_url.py` | With the documented URL the unmodified client dials exactly `api.novita.ai:443` (also for the unversioned `/openai` form); each form makes the client request a different path; a trailing slash; the span is identical for both of Novita's URL forms; a form the server does not route is an ERROR span, not a tracing fault; Langfuse's `/v3/openai` string; the span records neither host nor path |
| `tests/test_privacy.py` | A unique marker in every prompt, answer, tool argument and tool result: present by default, absent from every exported byte with `FI_HIDE_*`; no local path, user name or host name on successful calls; what the hide flags do not remove |
| `tests/test_page.py` | The Python snippet on the docs page runs as written (with the base URL swapped for the stand-in) and produces the span the page describes; page and app agree on the URL; the page names every URL form, keeps keys out, and has no em dashes |
| `tests/test_stub.py` | The stand-in only claims fields Novita documents |

```bash
.venv/bin/python -m pytest -q
```

## What is real and what is a stand-in

| Piece | Real | Stand-in |
| --- | --- | --- |
| `openai` SDK, `traceAI-openai`, `fi-instrumentation-otel`, OTLP export | yes | |
| Future AGI collector | yours | the tests use a recording collector |
| The Novita API | only if you set `NOVITA_API_KEY` without `NOVITA_BASE_URL` | `standin/novita_stub.py`, shaped from Novita's chat reference and Quickstart. Nothing in it was captured from a real Novita response. Which request paths it routes, the error envelope and the status for a wrong key are assumptions |
| `api.novita.ai` | the client dials it in `tests/test_base_url.py` | a refusing proxy answers 403; no tunnel opens |

What a live run is still needed for: which of `/openai/v1/chat/completions` and `/openai/chat/completions`
the service routes, the status and body for a wrong key, whether a request without `max_tokens` is
rejected, what a stream sends without `stream_options.include_usage`, whether reasoning tokens are inside
`usage.completion_tokens`, and whether the platform prices real Novita model ids.

## Versions

Tested 2026-10-15 on Python 3.13: traceAI-openai 0.1.10, fi-instrumentation-otel 1.1.0, openai 3.31.0 (latest)
and 1.109.1, opentelemetry-sdk 1.45.1. The suite also passes with traceAI PR 249 (open) overlaid; the two
assertions that differ are written to accept both.
