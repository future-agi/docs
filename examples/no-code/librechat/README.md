# LibreChat to Future AGI

Runnable assets for the docs page `src/pages/docs/integrations/no-code/librechat.mdx`.

LibreChat exports agent runs through its built-in Langfuse exporter and, optionally, backend spans through
its own OpenTelemetry SDK. Both go to one OpenTelemetry Collector, which sets the Observe project, maps the
Langfuse span shape, keeps content out by default and forwards to Future AGI. Nothing is added to LibreChat.

| File | What it is |
| --- | --- |
| `otelcol/otelcol.yaml` | The collector config the page ships (copied verbatim onto the page). |
| `env/futureagi.env.example` | The block for LibreChat's `.env` (copied verbatim onto the page). |
| `docker-compose.override.yml.example` | Adds the collector to LibreChat's own Compose stack (on the page). |
| `librechat.yaml`, `mcp/order_tools.mjs` | Test-only LibreChat config: one custom OpenAI-compatible endpoint and a two-tool MCP server (one tool always fails). |
| `compose.test.yml` | Smallest test stack: MongoDB, the LibreChat API image and the collector. |
| `run_e2e.sh` | The end-to-end test (below). |
| `drive_chat.py` | Drives one chat turn through LibreChat's HTTP API, the calls the web UI makes. |
| `tools/render_env.py` | Renders the test `.env` (fresh secrets plus the page's block) into `RUN_DIR`. |
| `tools/check_spans.py` | Checks what a self-hosted Future AGI stored (span types, model, tokens, tool name, session, user, errors). |
| `tools/scan_local_stack.py` | Privacy scan: every stored column of every row of a project, for given needles. |
| `tests/` | Unit tests, static checks of the shipped files against the page, and a contract test that runs the real collector on recorded LibreChat payloads. |

## Run the end-to-end test

Needs Docker with Compose (`docker compose` or `docker-compose`), a self-hosted Future AGI in Docker (the
checks read its Postgres and ClickHouse containers; set `FI_PG_CONTAINER` / `FI_CH_CONTAINER` if yours are not
named like the TH-8103 test stack), and any OpenAI-compatible model endpoint reachable from a container.

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
export FI_TRACES_URL=http://host.docker.internal:4318/v1/traces    # your Future AGI collector
export TEST_LLM_BASE_URL=http://host.docker.internal:8317/v1 TEST_LLM_API_KEY=... TEST_LLM_MODEL=gpt-6-luna
./run_e2e.sh
```

Legs:

1. **Content off** (project `$FI_PROJECT_NAME`, default `librechat-e2e`): a turn that calls the MCP tool, a
   turn whose tool fails, and a turn on a model the provider rejects. `check_spans.py` then requires agent,
   llm and tool spans, the model and token counts, a tool name, a session and an end user on every agent-run
   span, an `ERROR` span, the backend chat and stream spans, and no parentless background database spans.
   `scan_local_stack.py` scans every stored column for the prompt marker, the tool argument and result, the
   reply, the provider and tool error text, the user's name, email and username, this machine's host and
   user name, a local path and the Future AGI keys: none may be found.
2. **Content on** (project `<name>-content`): the collector is restarted with `FI_CAPTURE_CONTENT=true`; the
   prompt marker and the tool result must now be found, the keys and host details still not.
3. **Collector stopped**: a chat must still complete.

`KEEP=1` leaves the stack running. Evidence (turn summaries, span checks, scan counts, attribute-key
inventory) is written to `$RUN_DIR/evidence`.

## Run the tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q tests
```

`tests/test_collector_live.py` starts `otel/opentelemetry-collector-contrib:0.162.0` in Docker (skipped when
Docker or the image is missing), feeds it `tests/fixtures/*.json`, and checks what it forwards to a local sink:
uncompressed protobuf, the caller's credentials passed through, the project set, Langfuse attributes mapped to
span kinds, model, tokens, tool name and errors, content removed by default and present with the opt-in, and
client and host identifiers removed. The fixtures were recorded from LibreChat v0.8.8 (three test turns by a
test user against a test model; no real user data).
