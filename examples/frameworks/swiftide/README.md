# Swiftide → Future AGI

Runnable code for the docs page [Swiftide tracing with Future AGI](../../../src/pages/docs/integrations/frameworks/swiftide.mdx).
A Swiftide 0.33.0 agent with one tool (`get_weather`). The agent exports Swiftide's own `tracing`
spans with the Rust OpenTelemetry SDK to a local OpenTelemetry Collector, and `collector.yaml` maps
them to Future AGI span types, model names and token counts, removes content and forwards them.

| Path | |
| --- | --- |
| `Cargo.toml` | Swiftide with its structured span fields enabled, `tracing-opentelemetry` and the OTLP/HTTP exporter |
| `src/main.rs` | The agent; exports to `127.0.0.1:4318` and shuts the provider down before exit |
| `collector.yaml` | OpenTelemetry Collector Contrib configuration: field mapping, privacy filtering, Future AGI exporter |
| `tests/test_collector.py` | The built example and the Collector against a local mock model server and a local OTLP receiver |

## Run

Rust 1.97 or newer (Swiftide 0.33's minimum) and `otelcol-contrib` 0.164.0.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=swiftide-agent   # FI_TRACES_ENDPOINT for self-hosted
otelcol-contrib --config collector.yaml                                 # FI_CAPTURE_CONTENT=true to send content
```

In a second terminal:

```bash
export OPENAI_API_KEY=... MODEL=gpt-4o-mini   # OPENAI_BASE_URL for a compatible endpoint
cargo run -- "What is the weather in Paris right now?"
```

## Tests

The tests use only 127.0.0.1 and need port 4318 free.

```bash
cargo build
python3 -m venv .venv && .venv/bin/pip install opentelemetry-proto
.venv/bin/python tests/test_collector.py --collector "$(command -v otelcol-contrib)" \
  --binary target/debug/swiftide-futureagi-tracing
```
