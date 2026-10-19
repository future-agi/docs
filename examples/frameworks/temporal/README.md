# Temporal tracing example

Runnable assets for the docs page [Temporal tracing with Future AGI](../../../src/pages/docs/integrations/frameworks/temporal.mdx).
A Temporal workflow that plans with a model, runs a tool and answers with the model, as one trace in
Observe: Temporal's `StartWorkflow`, `RunWorkflow`, `StartActivity` and `RunActivity` spans (from
`OpenTelemetryPlugin`) with the model and tool spans of the activities under the activity that ran them.
This is tracing for your own Temporal application. It is not Future AGI's internal Temporal usage.

| File | What it is |
| --- | --- |
| `tracing.py` | The tracer provider: `create_tracer_provider` with the `project_name` resource, an OTLP/HTTP exporter with both key headers, the workflow id as session id, error text removed unless you opt in. Imported by the worker and the starter, never by workflow code. |
| `workflows.py` | `WeatherAgentWorkflow`. Imports only `temporalio` and the standard library; refers to the activities by name. |
| `activities.py` | `llm_plan`, `get_weather` (the tool) and `llm_answer`. Every model and tool call lives here. |
| `worker.py` | Worker with `OpenTelemetryPlugin(add_temporal_spans=True)`; flushes its spans on SIGTERM. |
| `starter.py` | Starts one workflow; flushes before exit. `--flaky` retries the tool, `--approval` waits for a signal. |
| `run_e2e.sh` | End-to-end run against a Future AGI you can read back (self-hosted): happy, replay, retry, failure, negative, projects, privacy and matrix scenarios |
| `tools/` | `wire_tap.py` (records what was sent: header names, never values), `wire_check.py` (headers, project, exactly-once), `check_trace.py` (hierarchy and counts of one stored workflow), `scan_local_stack.py` (privacy scan of every stored column), `marker_locations.py`, `replay_check.py` (Replayer with tracing on), `negative.py` (deliberately wrong setups) |
| `tests/` | Unit tests (no server, no network) and `test_contract_temporal.py`, which runs the real `temporalio` SDK against a Temporal dev server with a stub model and an in-memory exporter (`RUN_TEMPORAL_TESTS=1`) |

## Tested versions (2026-10-16)

| | |
| --- | --- |
| `temporalio` | 1.34.0 (latest, 2026-09-30), end to end: every scenario on Python 3.13.15, the `matrix` scenario (a run with no workflow cache) on Python 3.10.17; the 47 tests on both. 1.33.0 and 1.32.0 on Python 3.13: the unit and dev-server tests (47 passed), not the Future AGI run. 1.31.0 does not export `ReplaySafeTracerProvider` and is not supported. |
| Temporal server | `temporal server start-dev`: Temporal CLI 1.9.1, server 1.32.0 (macOS arm64, Homebrew) |
| Python packages | `fi-instrumentation-otel` 1.1.0, `traceai-openai` 0.1.10, `openai` 3.31.0, `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` 1.45.1 |
| Future AGI | self-hosted (local Docker stack), OTLP/HTTP `/tracer/v1/traces` |

## Run the tests

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-test.txt
pytest tests -q                              # unit tests: no server, no network
RUN_TEMPORAL_TESTS=1 pytest tests -q         # adds the Temporal dev-server contract tests (needs the `temporal` CLI)
```

## Run end to end

Needs the Temporal CLI, an OpenAI-compatible model endpoint, and a Future AGI whose storage the scan tool
can read (`FI_PG_CONTAINER`, `FI_CH_CONTAINER` name its containers).

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:<port>
export OPENAI_API_KEY=... OPENAI_BASE_URL=... MODEL=...
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all
# matrix legs: PYTHON_ALT=/path/to/py310/bin/python ./run_e2e.sh matrix
```

Or run it by hand against a dev server (`temporal server start-dev`) in three terminals:

```bash
python worker.py
python starter.py "What is the weather in Lisbon today?"
python starter.py "What is the weather in Lisbon today?" --flaky     # the tool fails once and is retried
```

Evidence (span dumps, wire captures, logs) goes to `./evidence`, which can contain prompts and must not be
committed. Content is never printed; key values are never written.
