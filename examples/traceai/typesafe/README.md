# TypeSafe (Jev) tracing example

Runnable companion to the docs page `src/pages/docs/integrations/traceai/typesafe.mdx`
(`/docs/integrations/traceai/typesafe`). It traces TypeSafe System One decision calls made with the
official `typesafe-sdk` Python client using the `traceAI-typesafe` instrumentor
([traceAI PR #264](https://github.com/future-agi/traceAI/pull/264)).

Status: alpha. **No TypeSafe account or API key was used.** The success path ran against the local
stand-in below; one failure case ran against the real `api.typesafe.ai` with a deliberately invalid key.

## Contents

| Path | What it is |
| --- | --- |
| `app.py` | The recipe the page shows (between the `--- ... start/end ---` markers) inside a small support-ticket triage app, with scenarios `ok`, `fail-422`, `fail-auth`, `fail-asset` |
| `run_e2e.sh` | Creates a venv, runs the tests, runs `app.py` against a Future AGI collector, optionally the privacy comparison and the real-API 401 probe |
| `standin/systemone_stub.py` | Local **STAND-IN** shaped like TypeSafe's published OpenAPI document (`POST /v1/systemone`, `GET /v1/models`, the real error bodies). Answers are hash-derived numbers, **not Jev** |
| `tests/` | pytest: the stand-in against the real SDK, `app.py` against a recording OTLP collector (spans, headers, no gzip, privacy markers), and page/example consistency |
| `requirements.txt` | Pinned versions the example was tested with |

## Run it

Python 3.10 to 3.13 (fi-instrumentation-otel 1.1.0 does not support 3.14).

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_BASE_URL=http://localhost:4318      # your Future AGI collector (run_e2e.sh defaults to this)
./run_e2e.sh                                    # tests, then app.py against the stand-in. No TypeSafe needed
PRIVACY=1 ./run_e2e.sh                          # also: hide flags on vs default, with a unique marker
REAL_AUTH_PROBE=1 ./run_e2e.sh                  # also: one invalid-key call to the real api.typesafe.ai (HTTP 401)
```

Against the real TypeSafe API (needs your own account and key; a run is billed by TypeSafe):

```bash
export TYPESAFE_API_KEY=...       # goes to the SDK only
./run_e2e.sh
```

Until `traceAI-typesafe` is on PyPI, `run_e2e.sh` installs it from the traceAI PR commit
(`TRACEAI_TYPESAFE` overrides the pip requirement, for example a local checkout:
`TRACEAI_TYPESAFE=/path/to/traceAI/python/frameworks/typesafe`).

## What is real and what is a stand-in

| Piece | Real or stand-in |
| --- | --- |
| `typesafe-sdk` client (0.7.5), `traceAI-typesafe`, `fi-instrumentation-otel` (`register()`), OTLP export | Real |
| Future AGI collector, storage and Observe UI | Real (a local Future AGI) |
| System One answers (`noul`, `choice`, `score`) | **STAND-IN** (`standin/systemone_stub.py`) |
| HTTP 401 for an invalid key | Real `api.typesafe.ai` with `REAL_AUTH_PROBE=1`; the stand-in otherwise |
| HTTP 422 validation error | STAND-IN, using the FastAPI error shape TypeSafe's OpenAPI document declares |
