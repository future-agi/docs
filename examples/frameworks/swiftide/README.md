# Swiftide → Future AGI (tracing recipe)

Runnable code for the docs page [Swiftide tracing with Future AGI](../../../src/pages/docs/integrations/frameworks/swiftide.mdx).
A Swiftide 0.33.0 agent with one tool (`get_weather`). Swiftide's `tracing` spans go through a
`tracing-opentelemetry` layer and the OTLP/HTTP exporter to Future AGI. Not a package: copy what you need.

| Path | |
| --- | --- |
| `src/lib.rs` | The recipe: exporter (both key headers, uncompressed protobuf), resource (`project_name`), batch provider, layer and filter, `ContentFilter` (content off by default) |
| `src/main.rs` | The agent; shuts the provider down before exit |
| `tests/contract.rs` | Real Swiftide agent against a mock OpenAI-compatible server, spans in memory: tree shape, ERROR on failures, content off/on, provider key never exported, no `langfuse` in the build |
| `tests/export.rs` | Real OTLP exporter against a local receiver: headers, no `Content-Encoding`, protobuf body with `project_name`; nothing sent before `shutdown()`; exporter failure does not panic |
| `tests/page.rs` | Every line of the page's code blocks exists in these files |
| `tests/fixtures/`, `tests/replay/` | One recorded, content-free span tree from a real run, checked offline and optionally replayed into a Future AGI |
| `run_e2e.sh`, `tools/` | End-to-end runs against a real Future AGI and a real model endpoint |

## Run

Rust 1.97 or newer (Swiftide 0.33's minimum).

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=swiftide-agent   # FI_BASE_URL for self-hosted
export OPENAI_API_KEY=... MODEL=gpt-4o-mini                               # OPENAI_BASE_URL for a compatible endpoint
cargo run -- "What is the weather in Paris right now?"
TRACE_CONTENT=true cargo run -- "..."                                      # opt in to message content
```

## Tests

```bash
cargo test                                   # 13 tests, no network beyond 127.0.0.1
python3 -m venv .venv && .venv/bin/pip install -r tests/replay/requirements.txt
.venv/bin/pytest tests/replay -q             # fixture checks; RUN_FI_REPLAY=1 (+ FI_*) also posts it
```

## End to end

`run_e2e.sh` builds the example and runs it through `tools/wire_tap.py` (records what is sent, header
names only) into your Future AGI:

| Scenario | What it shows |
| --- | --- |
| `main` | An answer with a tool call, a failed tool call, an unknown model: tree and ERROR statuses (`tools/check_trace.py`), wire checks (`tools/wire_summary.py`) |
| `privacy` | A unique marker in the question, the tool arguments and the provider error, with backtraces on: absent from every stored column with the defaults, present with `TRACE_CONTENT=true`; user/host/paths/backtraces/keys absent in both (`tools/scan_local_stack.py`); the opt-in marker only in its own project (`tools/isolation_check.py`) |
| `no-shutdown` | Without `provider.shutdown()` the root span never leaves the process |
| `exporter-down` | Nothing listening on the Future AGI URL: the agent still answers and exits 0 |
| `matrix` | The same `main` scenario on another Swiftide release (default 0.32.1) |

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:<port> OPENAI_API_KEY=... MODEL=... \
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all
```

`VERIFY` (a script that reads the stack's database) and the `privacy` scenario need `docker exec`
access to a self-hosted Future AGI's Postgres and ClickHouse containers (`FI_PG_CONTAINER`,
`FI_CH_CONTAINER`). Evidence goes to `./evidence/` (`EVIDENCE=...`), which is not committed.
