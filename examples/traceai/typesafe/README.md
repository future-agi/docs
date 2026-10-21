# TypeSafe (Jev) tracing example

Runnable companion to the docs page `src/pages/docs/integrations/traceai/typesafe.mdx`
(`/docs/integrations/traceai/typesafe`). It traces TypeSafe System One decision calls made with the
official `typesafe-sdk` Python client using the `traceAI-typesafe` instrumentor
([traceAI PR #264](https://github.com/future-agi/traceAI/pull/264)).

Status: verified against the live TypeSafe API on 2026-10-17 (typesafe-sdk 0.7.5, model `jev-1.13.0`): two real
decisions (sync and async), a real 422 and a real 401, traced into a local Future AGI. The default `./run_e2e.sh`
(no `TYPESAFE_API_KEY`) still uses the local STANDIN server below, so it needs no account. Not yet seen live: 429
(`retry_after_ms`), `box` answers, image assets.

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

Against the real TypeSafe API (needs your own account and key; a run is billed by TypeSafe, two decisions of a few hundred tokens each):

```bash
export TYPESAFE_API_KEY=...       # goes to the SDK only
./run_e2e.sh
```

`run_e2e.sh` installs `traceAI-typesafe==0.1.0` from PyPI. `TRACEAI_TYPESAFE` overrides
that pip requirement, for example with a local checkout:
`TRACEAI_TYPESAFE=/path/to/traceAI/python/frameworks/typesafe`.

## What is real and what is a stand-in

| Piece | Real or stand-in |
| --- | --- |
| `typesafe-sdk` client (0.7.5), `traceAI-typesafe`, `fi-instrumentation-otel` (`register()`), OTLP export | Real |
| Future AGI collector, storage and Observe UI | Real (a local Future AGI) |
| System One answers (`noul`, `choice`, `score`) | **Real** `api.typesafe.ai` when `TYPESAFE_API_KEY` is set (verified 2026-10-17); **STANDIN** (`standin/systemone_stub.py`, hash-derived numbers, not Jev) otherwise, and in `tests/` |
| HTTP 401 for an invalid key | Real `api.typesafe.ai` (`REAL_AUTH_PROBE=1`, or any run with a key set); the stand-in otherwise |
| HTTP 422 validation error | Real `api.typesafe.ai` when a key is set; STANDIN otherwise (FastAPI error shape from TypeSafe's OpenAPI document) |
