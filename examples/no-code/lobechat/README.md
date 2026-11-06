# LobeHub (LobeChat) -> Future AGI

Recipe and end-to-end test for sending LobeHub's server-side agent runs to Future AGI Observe.
The docs page is `src/pages/docs/integrations/no-code/lobechat.mdx`.

## Files

| File | What it is |
| --- | --- |
| `otelcol/otelcol.yaml` | The OpenTelemetry Collector (contrib) config the page ships: keeps LobeHub's agent runtime spans and the request that started the run, makes that request the trace root, sets the project, span types and session, keeps error text and agent descriptions out unless `FI_CAPTURE_CONTENT=true`, discards LobeHub's metrics, forwards uncompressed OTLP with LobeHub's own keys. |
| `docker-compose.override.yml.example` | Adds the collector to LobeHub's Docker Compose deployment (`docker-compose/deploy`). |
| `env/futureagi.env.example` | The five variables for LobeHub's `.env`. |
| `compose.test.yml` | Test stack: LobeHub (Gateway Mode), its Agent Gateway, ParadeDB Postgres, Redis and the collector, memory-capped. |
| `run_e2e.sh` | Full end-to-end run against a self-hosted Future AGI in Docker (three legs: content off, content on, collector down). |
| `mcp/order_tools.py` | Test MCP server (Streamable HTTP): `get_order_status`, and `cancel_order` which always fails. |
| `tools/drive_lobehub.py` | Starts real agent runs: Better Auth sign-up, tRPC to add the MCP server and set the model, `POST /api/agent`, waits for each run. |
| `tools/check_spans.py` | Checks the stored spans (hierarchy, types, model, tokens counted once, tool name, session, errors, clean resource). |
| `tools/scan_local_stack.py` | Privacy scan: every column of every stored row of the project, for marker strings. |
| `tests/` | Unit tests, static checks of the files and the page, and `test_collector_live.py`, which runs the real collector in Docker on spans recorded from LobeHub v2.2.19 (`tests/fixtures/`). |

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q tests            # needs Docker for test_collector_live.py

export FI_API_KEY=... FI_SECRET_KEY=... FI_TRACES_URL=http://host.docker.internal:4318/v1/traces
export TEST_LLM_BASE_URL=http://host.docker.internal:<port>/v1 TEST_LLM_API_KEY=... TEST_LLM_MODEL=<model>
PYTHON=.venv/bin/python ./run_e2e.sh           # LOBEHUB_VERSION=2.2.18 for the older release
```

`run_e2e.sh` generates the LobeHub secrets its own `setup.sh` would (auth secret, key vault secret,
gateway token, an RS256 JWKS pair), runs everything under the Compose project `lobehub-futureagi-e2e`
and removes the stack and its volumes at the end (`KEEP=1` keeps it). The stored-data checks read the
Postgres and ClickHouse containers of a self-hosted Future AGI (`FI_PG_CONTAINER`, `FI_CH_CONTAINER`).
On Linux Docker, set `ORDER_TOOLS_HOST=0.0.0.0` and `SINK_HOST=0.0.0.0` so containers reach the test
servers through `host.docker.internal`.
