# BytePlus ModelArk tracing example

Runnable companion to the docs page `src/pages/docs/integrations/providers/byteplus.mdx`
(`/docs/integrations/providers/byteplus`). It traces BytePlus ModelArk chat completions made with the
stock `openai` Python client and the existing `traceAI-openai` instrumentor. There is no BytePlus
package and no `traceai-byteplus`.

Status: alpha. **No BytePlus account was used and no request was ever sent to a BytePlus host.** See
"What is real and what is a stand-in" below.

## Contents

| Path | What it is |
| --- | --- |
| `app.py` | The recipe (about 10 lines of integration) plus scenarios: `chat`, `stream`, `tools`, `thinking`, `error` |
| `run_e2e.sh` | Creates a venv, runs the tests, runs `app.py` against a collector, optionally runs the privacy comparison |
| `standin/byteplus_modelark_stub.py` | Local STAND-IN shaped like the ModelArk Chat API (`/api/v3/chat/completions`). Not BytePlus |
| `standin/connect_probe.py` | Refusing HTTP proxy that records which host the unmodified client dials. Opens no tunnel |
| `tests/` | pytest suite (see below) |
| `requirements.txt` | Pinned versions the example was tested with |

## Run it

Python 3.10 to 3.13 (traceAI-openai 0.1.10 does not support 3.14).

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_BASE_URL=http://localhost:4318        # your Future AGI collector (run_e2e.sh defaults to this)
./run_e2e.sh                                      # tests, then app.py against the stand-in. No BytePlus needed
PRIVACY=1 ./run_e2e.sh                            # also: content capture off vs default, with a unique marker
```

Against the real BytePlus API (needs your own account, activated ModelArk and a key; this can cost money,
and the script never creates an account):

```bash
export ARK_API_KEY=...            # BytePlus ModelArk key, goes to the OpenAI client only
export ARK_MODEL=...              # Model ID or endpoint ID from your ModelArk console
export ARK_REGION=ap              # ap (Johor, default) or eu (Dublin): must match the region that issued the key
./run_e2e.sh
```

Any OpenAI-compatible server can stand in for the target: set `ARK_BASE_URL`, `ARK_API_KEY` and `ARK_MODEL`.
`ARK_BASE_URL` containing `/api/coding` is refused: that is the Coding Plan, not this recipe.

Run a single scenario with `APP_ARGS="--scenario stream"`. `python app.py --help` lists the flags.

## What the tests cover

| File | Covers |
| --- | --- |
| `tests/test_recipe.py` | Region URLs and default; Coding Plan URLs refused; trace shape (AGENT, LLM, TOOL, one session); model and usage; streaming usage; `thinking` in `extra_body`; error span; provider label `openai`; keys go only where they belong; uncompressed OTLP with `project_name`; an unreachable collector never breaks the request |
| `tests/test_regions.py` | With the documented AP and EU URLs, the unmodified client dials exactly `ark.ap-southeast.bytepluses.com:443` / `ark.eu-west.bytepluses.com:443`, never the other region; the span records neither host |
| `tests/test_privacy.py` | A unique marker in every prompt, answer, tool argument and tool result: present by default, absent from every exported byte with `FI_HIDE_*`; what the hide flags do not remove |
| `tests/test_page.py` | The Python snippet on the docs page runs as written (with the base URL swapped for the stand-in) and produces the span the page describes |
| `tests/test_stub.py` | The stand-in only claims fields BytePlus documents |
| `tests/test_ark_sdk.py` | Optional (`pip install arkruntime`): BytePlus's own `Ark` client is not traced by traceAI-openai |

```bash
.venv/bin/python -m pytest -q
```

## What is real and what is a stand-in

| Piece | Real | Stand-in |
| --- | --- | --- |
| `openai` SDK, `traceAI-openai`, `fi-instrumentation-otel`, OTLP export | yes | |
| Future AGI collector | yours | the tests use a recording collector |
| The ModelArk API | only if you set `ARK_API_KEY` without `ARK_BASE_URL` | `standin/byteplus_modelark_stub.py`, shaped from BytePlus's Chat API reference. Nothing in it was captured from a real BytePlus response. The `{"error": {...}}` envelope is an assumption |
| BytePlus hostnames | the client dials them in `tests/test_regions.py` | a refusing proxy answers 403; no tunnel opens |

What a live run is still needed for: the exact `model` value ModelArk returns for an endpoint id, whether
reasoning tokens are inside `usage.completion_tokens`, the real error body for a cross-region key, and
whether the real SSE stream matches the stand-in's.

## Versions

Tested 2026-10-15 on Python 3.13: traceAI-openai 0.1.10, fi-instrumentation-otel 1.1.0, openai 3.31.0 (latest)
and 1.109.1, opentelemetry-sdk 1.45.1. The suite also passes with traceAI PR 249 (open) overlaid; the two
assertions that differ are written to accept both.
