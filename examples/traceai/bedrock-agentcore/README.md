# Amazon Bedrock AgentCore Runtime → Future AGI

Runnable example for the docs page
[Trace Amazon Bedrock AgentCore Runtime](https://docs.futureagi.com/docs/integrations/traceai/bedrock-agentcore).
Alpha: local-validated against a self-hosted Future AGI; no AgentCore Runtime was deployed (AWS
validation pending).

| File | What it is |
| --- | --- |
| `agentcore_tracing.py` | The helper you copy next to your agent: `keep_future_agi_exporter`, `traced_invocation`, `traced_stream`, `ErrorTypeOnlyExporter`. |
| `agent_langchain.py` | Path A: a LangChain agent with one tool, traced with `register()` + `traceAI-langchain`. |
| `agent_strands.py` | Path B: a Strands agent with one tool, exported by Strands' own OpenTelemetry over plain OTLP. |
| `Dockerfile` | The runtime container shape (arm64 when built on arm64, uid 1000, port 8080) without the ADOT wrapper, like `agentcore configure --disable-otel` generates. |
| `requirements.txt` | Pinned versions both paths were tested with. |
| `tests/` | 29 contract tests against the real `BedrockAgentCoreApp` (in-process, in-memory exporters). |
| `run_e2e.sh` | End-to-end run against a self-hosted Future AGI you can read back: happy, failure, content off/on, failure with content off, unreachable collector. |
| `tools/` | `invoke.py` (calls `/invocations` like the runtime), `check_trace.py` (trace shape), `scan_columns.py` (counts rows that contain a needle in any stored column of a self-hosted Future AGI). |

## Tests

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q tests
```

## Run one agent locally

```bash
export DISABLE_ADOT_OBSERVABILITY=true FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=agentcore-demo
export OPENAI_API_KEY=... AGENT_MODEL=gpt-4o-mini      # OPENAI_BASE_URL for any OpenAI-compatible endpoint
.venv/bin/python agent_langchain.py                     # :8080
python tools/invoke.py http://127.0.0.1:8080 my-session-0001 "What is the status of order A-100?"
```

For path B set the `OTEL_EXPORTER_OTLP_*`, `OTEL_RESOURCE_ATTRIBUTES` and
`OTEL_SEMCONV_STABILITY_OPT_IN` variables listed at the top of `agent_strands.py` instead of `FI_*`.

## End to end

```bash
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py \
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:8000 \
OPENAI_API_KEY=... OPENAI_BASE_URL=... AGENT_MODEL=... \
./run_e2e.sh all                      # or langchain | strands
```

`CONTAINER=1 IN_CONTAINER_FI_BASE_URL=http://host.docker.internal:<port> IN_CONTAINER_OPENAI_BASE_URL=...`
runs the happy and failure scenarios inside the image built from the Dockerfile. Keys are passed
to the container by name (`docker run -e FI_API_KEY`), never baked into it.

The privacy scan (`tools/scan_columns.py`) reads the ClickHouse and Postgres containers of a
self-hosted Future AGI through `docker exec` (`FI_CH_CONTAINER`, `FI_PG_CONTAINER`).
