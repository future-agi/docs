# IBM watsonx Orchestrate ADK tracing example

Runnable assets for the docs page [IBM watsonx Orchestrate ADK tracing with Future AGI](../../../src/pages/docs/integrations/frameworks/watsonx-orchestrate-adk.mdx).
A LangGraph agent instrumented with the watsonx Orchestrate Agentic SDK (`ibm-watsonx-orchestrate-sdk`)
exports its spans to `WXO_OTLP_ENDPOINT`; an OpenTelemetry Collector names the Observe project, maps
the SDK's span kinds, removes content unless `KEEP_WXO_CONTENT=true`, and forwards to Future AGI.

| File | What it is |
| --- | --- |
| `agent.py` | LangGraph weather agent: `@trace_agent_call` node, `tracer.start_llm_span` model call with token counts, `@trace_tool_call` tool that fails for unknown cities, one root span per request, `tracer.shutdown()` on exit |
| `otelcol.yaml` | Collector config: stamps `project_name`, maps `span.kind` to Future AGI span kinds, removes stack traces always and content/error text/user ids by default, holds the Future AGI keys, never forwards incoming headers, uncompressed export, no self-metrics |
| `run_e2e.sh` | End-to-end run against a Future AGI you can read back (self-hosted): `collector`, `optin`, `direct`, `lifecycle` and `matrix` scenarios |
| `tools/` | `wire_tap.py` (records what was sent: header names, never values), `wire_summary.py`, `check_trace.py` (one trace per run, span kinds under the right parents, model/tokens, errors, content off), `scan_local_stack.py` (privacy scan of every stored column), `client_mode_run.py` (the agent with a Client-mode tracer and a placeholder bearer token) |
| `tests/` | Unit tests (no network, no Docker): the agent's span tree with the real SDK and a scripted model, the collector config, the page, the tools. `test_collector_replay.py` replays a recorded SDK 2.18.2 export through the real collector (`RUN_DOCKER_TESTS=1`) |

## Tested versions (2026-10-16)

| | |
| --- | --- |
| Agentic SDK | `ibm-watsonx-orchestrate-sdk` 2.18.2 (latest) on Python 3.12.10, and 2.18.0 (with `-core`/`-clients` 2.18.0) on Python 3.13.15 |
| Python packages | `langgraph` 1.2.15, `langchain-openai` 1.7.2, `langchain-core` 1.6.11, `opentelemetry-sdk` 1.45.1, `opentelemetry-exporter-otlp-proto-http` 1.45.1 |
| Collector | `otel/opentelemetry-collector-contrib:0.162.0` (Docker, 256 MB) |
| Future AGI | self-hosted (local Docker stack), OTLP/HTTP `/tracer/v1/traces` |

## Run the tests

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-test.txt
pytest tests -q                       # unit tests, no network, no Docker
RUN_DOCKER_TESTS=1 pytest tests -q    # adds the collector replay (needs Docker Desktop or colima)
```

## Run end to end

Needs Docker, an OpenAI-compatible model endpoint, and a Future AGI whose storage the scan tool can
read (`FI_PG_CONTAINER`, `FI_CH_CONTAINER` name its containers).

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:<port>
export OPENAI_API_KEY=... OPENAI_BASE_URL=... MODEL=...
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all
# matrix leg: PYTHON_ALT=/path/to/other-venv/bin/python ./run_e2e.sh matrix
```

Evidence (span dumps, wire captures, logs) goes to `./evidence`, which contains prompts and must not
be committed. Content is never printed; key values are never written.
