# Graphite (grafi) with Future AGI tracing

Runnable companion to the docs page `docs/integrations/frameworks/graphite`: trace a [Graphite](https://github.com/binome-dev/graphite) agent in Future AGI. Graphite is the Binome agent framework (PyPI `grafi`, repository `binome-dev/graphite`, MPL-2.0). It is not Graphite.dev, the code-review product. There is no traceAI package for it.

Graphite emits OpenTelemetry spans through the tracer in its `ExecutionServices`, so the application owns the tracer provider. Graphite's own `setup_tracing()` helper cannot be used for Future AGI: it opens a plaintext gRPC exporter with no headers and sets `service.name` instead of `project_name`. `futureagi_grafi.py` builds the right provider: `project_name` on the resource, `X-Api-Key` and `X-Secret-Key` on an OTLP/HTTP exporter, no gzip, and an exporter wrapper that maps Graphite's attribute names to the ones Future AGI reads and keeps prompts, answers, tool payloads and error text out of the export unless you opt in.

## Layout

| Path | What it is |
| --- | --- |
| `futureagi_grafi.py` | `create_tracer_provider()`: the provider, the exporter, and `GrafiExporter` (renames Graphite's keys, drops dict values, metadata only by default, `FI_CAPTURE_CONTENT=1` to opt in). The page shows this file. |
| `quickstart.py` | A complete Graphite assistant (one LLM node, one function tool) run through `GrafiRuntime`, with the tracer injected. The page shows its tracing part. |
| `app.py` | The same assistant with three scenarios: `chat`, `tool-error`, `model-error`. Used by the tests and `run_e2e.sh`. |
| `tests/` | 44 tests: contract (hierarchy, span kinds, session, empty ids, dict attribute, headers, path, no gzip, errors, flush, dead collector, two projects, provider instrumentor), privacy marker scans of every byte the collector receives, an attribute drift guard, mapping unit tests, and a check that `setup_tracing` is never used. No Future AGI stack needed. |
| `tests/fake_openai.py` | A small OpenAI-compatible server for the tests (tool call, answer, usage, an error model). Not OpenAI. |
| `run_e2e.sh` | Tests, then the agent against a real model and a real Future AGI collector. |

## Install

Python 3.11, 3.12 or 3.13.

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt     # pins grafi 0.0.36
```

## Run

Tests only (no network, no keys):

```bash
python -m pytest
```

End to end against a Future AGI collector (self-hosted shown) and a model:

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
OPENAI_API_KEY=... OPENAI_BASE_URL=... OPENAI_MODEL=... ./run_e2e.sh
```

`run_e2e.sh` creates `.venv` if there is none, runs the tests, runs `app.py` three times into project `graphite-e2e` (or `FI_PROJECT_NAME`), then once with `FI_CAPTURE_CONTENT=1` into `<project>-content`, and once with the OpenInference OpenAI instrumentor on into `<project>-provider`. Without `OPENAI_API_KEY` it starts the local stand-in from `tests/fake_openai.py`, which is not a real model, so the script runs anywhere.

Another grafi version: `VENV_DIR=/path/to/venv ./run_e2e.sh` with a venv that has the version you want.

## Configure

| Variable | Required | Purpose |
| --- | --- | --- |
| `FI_API_KEY`, `FI_SECRET_KEY` | Yes | Future AGI key pair. Sent as `X-Api-Key` and `X-Secret-Key` to the collector only. |
| `FI_PROJECT_NAME` | No | Observe project. Default `graphite-app`. |
| `FI_BASE_URL` | No | Collector origin. Traces go to `$FI_BASE_URL/tracer/v1/traces`. Default `https://api.futureagi.com`. |
| `FI_CAPTURE_CONTENT` | No | `1` exports prompts, answers, tool arguments and results, and error text. Default off. |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | For the model | Any OpenAI-compatible endpoint, used by `app.py` and `quickstart.py`. |
| `GRAFI_SPAN_DISABLE_PAYLOADS`, `GRAFI_SPAN_MAX_PAYLOAD_CHARS` | No | Graphite's own switches for span payloads. They apply before the recipe sees the span. |

## Privacy

Graphite always writes the full serialized input and output of every component onto its spans, and the text and traceback of an error. `GrafiExporter` removes them before export unless `FI_CAPTURE_CONTENT=1`. It keeps an allow-list of metadata attributes (`METADATA_ATTRIBUTES`), so an attribute a later Graphite release adds stays private until reviewed, and `tests/test_privacy.py::test_every_attribute_graphite_sets_is_classified` fails when that happens. A stack trace and Graphite's raw error dumps (`error`, `error.stack`, `error.details`) are never exported, in either mode.

`session.id` (Graphite's `conversation_id`) and `user.id` (its `user_id`) are identifiers you set. They are exported in both modes. Use opaque ids, not email addresses.

## Not Graphite's `setup_tracing`

`tests/test_no_setup_tracing.py` fails if any file in this folder refers to `setup_tracing`, and runs the quickstart with every entry point of Graphite's helper replaced by a function that raises.
