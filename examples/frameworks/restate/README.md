# Restate tracing example

Runnable assets for the docs page [Restate tracing with Future AGI](../../../src/pages/docs/integrations/frameworks/restate.mdx).
One Restate invocation becomes one trace in Observe: Restate's `ingress`, `invocation-start`,
`invocation-attempt` and `invocation-end` spans, with the service's model and tool spans under the
attempt that ran them.

| File | What it is |
| --- | --- |
| `agent_service.py` | A Restate Virtual Object (`WeatherAgent/{key}/ask`) that calls a model and a tool in `ctx.run` steps, traced with traceAI through `restate.ext.tracing.RestateTracerProvider`. Exits and flushes on SIGTERM. |
| `restate.toml` | Server config: OTLP/HTTP endpoint (the collector) and the two Future AGI key headers |
| `otelcol.yaml` | OpenTelemetry Collector config: stamps `project_name`, removes host names, addresses, stack traces, and (unless `KEEP_RESTATE_DETAILS=true`) error text and object keys; passes the senders' key headers through; uncompressed export; no self-metrics |
| `run_e2e.sh` | End-to-end run against a Future AGI you can read back (self-hosted): collector, privacy, direct, lifecycle and matrix scenarios |
| `tools/` | `wire_tap.py` (records what was sent: header names, never values), `wire_summary.py`, `check_trace.py` (one trace per invocation, parents, no replay duplicates), `scan_local_stack.py` (privacy scan of every stored column) |
| `tests/` | Unit tests (no network, no Docker) and `test_collector_replay.py`, which replays a recorded Restate 1.8.0 trace through the real collector container (`RUN_DOCKER_TESTS=1`) |

## Tested versions (2026-10-15)

| | |
| --- | --- |
| Restate server | 1.8.0 (latest on 2026-10-15, released 2026-10-14) and 1.7.13, release binaries `restate-server-aarch64-apple-darwin` |
| `restate-sdk` | 1.0.5 (latest on 2026-10-15), Python 3.13.15 and 3.10.17. 1.1.0 (2026-10-21): unit tests only (`pytest tests`), not run end to end |
| Python packages | `hypercorn` 0.18.0, `fi-instrumentation-otel` 1.1.0, `traceai-openai` 0.1.10, `openai` 3.31.0, `opentelemetry-sdk` 1.45.1 |
| Collector | `otel/opentelemetry-collector-contrib:0.162.0` (Docker, 256 MB) |
| Future AGI | self-hosted (local Docker stack), OTLP/HTTP `/tracer/v1/traces` |

## Run the tests

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-test.txt
pytest tests -q                       # unit tests, no network, no Docker
RUN_DOCKER_TESTS=1 pytest tests -q    # adds the collector replay (needs Docker Desktop or colima)
```

## Run end to end

Needs a `restate-server` binary, Docker, an OpenAI-compatible model endpoint, and a Future AGI whose
storage the scan tool can read (`FI_PG_CONTAINER`, `FI_CH_CONTAINER` name its containers).

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:<port>
export OPENAI_API_KEY=... OPENAI_BASE_URL=... MODEL=...
PYTHON=.venv/bin/python RESTATE_SERVER=/path/to/restate-server VERIFY=/path/to/fi_verify.py \
  ./run_e2e.sh all
# matrix legs: RESTATE_SERVER_ALT=/path/to/restate-server-1.7.13 PYTHON_ALT=/path/to/py310/bin/python ./run_e2e.sh matrix
```

Evidence (span dumps, wire captures, logs) goes to `./evidence`, which can contain prompts and must
not be committed. Content is never printed; key values are never written.
