# Z.ai tracing example

Runnable companion to the docs page `src/pages/docs/integrations/providers/z-ai.mdx`
(`/docs/integrations/providers/z-ai`). It traces Z.ai general-platform chat completions made with the
stock `openai` Python client and the existing `traceAI-openai` instrumentor. There is no Z.ai
package, no `traceai-zai` and no `zai-sdk` dependency.

Status: alpha. Verified against the real `api.z.ai` general platform on 2026-10-17 with the free
`glm-4.7-flash` model (see "Live vendor verification" on the docs page). The local stand-in is still
used by the tests and by the default `./run_e2e.sh`, and is not Z.ai.

## Contents

| Path | What it is |
| --- | --- |
| `app.py` | The recipe (about 10 lines of integration) plus scenarios: `chat`, `stream`, `tools`, `thinking`, `error` |
| `run_e2e.sh` | Creates a venv, runs the tests, runs `app.py` against a collector, optionally runs the privacy comparison |
| `standin/zai_stub.py` | Local STAND-IN shaped like the Z.ai chat API (`/api/paas/v4/chat/completions`). Not Z.ai |
| `standin/connect_probe.py` | Refusing HTTP proxy that records which host the unmodified client dials. Opens no tunnel |
| `tests/` | pytest suite (see below) |
| `requirements.txt` | Pinned versions the example was tested with |

## Run it

Python 3.10 to 3.13 (traceAI-openai 0.1.10 does not support 3.14).

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_BASE_URL=http://localhost:4318        # your Future AGI collector (run_e2e.sh defaults to this)
./run_e2e.sh                                      # tests, then app.py against the stand-in. No Z.ai needed
PRIVACY=1 ./run_e2e.sh                            # also: content capture off vs default, with a unique marker
```

Against the real Z.ai API (needs your own account and key; a paid model costs money, and the script
never creates an account):

```bash
export ZAI_API_KEY=...            # Z.ai general platform key, goes to the OpenAI client only
export ZAI_MODEL=...              # a current model code from Z.ai's model list
./run_e2e.sh                      # calls https://api.z.ai/api/paas/v4/
```

Any OpenAI-compatible server can stand in for the target: set `ZAI_BASE_URL`, `ZAI_API_KEY` and
`ZAI_MODEL`. A `ZAI_BASE_URL` that is one of the three GLM Coding Plan URLs
(`https://api.z.ai/api/anthropic`, `https://api.z.ai/api/coding/paas/v4`, `https://api.z.ai/api/v1`, or
anything under them) is refused: that is a different Z.ai product, not this recipe.

Run a single scenario with `APP_ARGS="--scenario stream"`. `python app.py --help` lists the flags.

## What the tests cover

| File | Covers |
| --- | --- |
| `tests/test_recipe.py` | The base URL constant; the three Coding Plan URLs refused (and nothing exported or sent); trace shape (AGENT, LLM, TOOL, one session); model and usage; streaming usage from the last chunk with no `stream_options`; a stream that ends with `finish_reason: network_error`; `thinking` in `extra_body`; error span; provider label `openai`; keys go only where they belong; uncompressed OTLP with `project_name`; an unreachable collector never breaks the request. Runs against both stand-in shapes (documented fields only, and with the OpenAI `object` field) |
| `tests/test_host.py` | The fixture check: the real client built with the documented base URL, no network (mock transport), asserts the URL, the bearer header, the model, `project_name` and the provider label `openai`; the URL with and without the trailing slash; the async client; a Coding Plan URL is traced the same way, which is why the page warns |
| `tests/test_hosts_dialed.py` | With the documented URL, the unmodified client dials exactly `api.z.ai:443` (refusing proxy, nothing leaves the machine), and the span does not record the host |
| `tests/test_privacy.py` | A unique marker in every prompt, answer, tool argument and tool result: present by default, absent from every exported byte with `FI_HIDE_*`; what the hide flags do not remove |
| `tests/test_page.py` | The page has the required sections, URLs and flags; the Python snippet on the page runs as written (base URL swapped for the stand-in) and produces the span the page describes; no credentials in the page or the example |
| `tests/test_stub.py` | The stand-in only claims fields Z.ai documents, and answers the documented error codes |
| `tests/test_zai_sdk.py` | Optional (`pip install zai-sdk`): Z.ai's own `ZaiClient` is not traced by traceAI-openai |

```bash
.venv/bin/python -m pytest -q
```

## What is real and what is a stand-in

| Piece | Real | Stand-in |
| --- | --- | --- |
| `openai` SDK, `traceAI-openai`, `fi-instrumentation-otel`, OTLP export | yes | |
| Future AGI collector | yours | the tests use a recording collector |
| The Z.ai API | `ZAI_API_KEY` without `ZAI_BASE_URL`; run live 2026-10-17 (chat, stream, tools, thinking, 401, 429) | `standin/zai_stub.py`, shaped from Z.ai's chat completion reference, streaming guide and error table (read 2026-10-15). Nothing in it was captured from a real Z.ai response. Error messages come from the documented table; the body returned for each case on the live API was not checked |
| `api.z.ai` hostname | the client dials it in `tests/test_hosts_dialed.py` | a refusing proxy answers 403; no tunnel opens |

Proven live 2026-10-17: the `model` value returned, usage on the last stream chunk, reasoning tokens inside
`usage.completion_tokens`, the 401 and 429 error bodies. Still not proven live: `finish_reason: network_error`
streams, cost for GLM ids, paid models, other Z.ai APIs.

## Versions

Tested 2026-10-15: traceAI-openai 0.1.10, fi-instrumentation-otel 1.1.0, opentelemetry-sdk 1.45.1,
Python 3.13 with openai 3.31.0 (latest), and Python 3.10 with openai 1.109.1. The suite also passes with
traceAI PR 249 (open, head 88ceb5a) overlaid. zai-sdk 0.2.3
was used only for `tests/test_zai_sdk.py`.
