# goose application session tracing

goose has a built-in OpenTelemetry exporter. It sends to a local
OpenTelemetry Collector, which removes the OS user name, host name, and
log-line span events goose always attaches, then forwards to Future AGI. This
folder holds the collector config, the goose settings, a script that runs one
real session through both, and tests built from a recorded goose 1.54.0
export.

Docs page: `src/pages/docs/integrations/coding-agents/goose.mdx`.

| File | What it is |
| --- | --- |
| `otel-collector.yaml` | The collector: adds the Future AGI keys and project, deletes `user.name`, `host.name`, `session.user`, `session.host`, drops span events, labels `invoke_agent` spans as agents, traces only. |
| `futureagi-otel.env` | The goose side: OTLP endpoint of the local collector, traces only, content off. |
| `run_e2e.sh` | Starts the collector, runs one `goose run` with the recipe in a throwaway folder, stops the collector, and prints a marker string to search for. Needs a configured goose, `otelcol-contrib`, and `FI_API_KEY` / `FI_SECRET_KEY`. |
| `record_otlp.py` | Loopback OTLP/HTTP receiver. Decodes what goose sends and writes span names, parents, and attribute keys, with values dropped except for a structural allowlist. |
| `fixtures/goose-1.54.0-default.json` | Recorded from a real goose 1.54.0 run with the recipe (content off). |
| `fixtures/goose-1.54.0-content.json` | Same run with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. Values are still dropped; only the keys show content was exported. |
| `fixtures/goose-1.54.0-anthropic.json` | Same prompt with goose's Anthropic provider (content off): the tree is the same, only `gen_ai.provider.name` and the model change. |
| `test_contract.py`, `run_contract.sh` | Offline test of the span tree and the privacy default against the fixtures. |
| `test_collector.py`, `collector-test-overrides.yaml` | Runs `otel-collector.yaml` in a real `otelcol-contrib` on a payload rebuilt from the fixtures and checks that the user name, host name, and span events are gone (skipped without `otelcol-contrib`). |

## Run the contract test

```bash
./run_contract.sh                      # stdlib only; the collector test needs otelcol-contrib on PATH or OTELCOL_BIN
pip install opentelemetry-proto && ./run_contract.sh   # also tests record_otlp.summarize
```

## Re-record fixtures for a new goose version

```bash
python3 record_otlp.py --port 4319 --out fixtures/goose-<version>-default.json --seconds 90 &
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4319/v1/traces \
OTEL_TRACES_EXPORTER=otlp OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none \
OTEL_RESOURCE_ATTRIBUTES=project_name=goose-fixture,project_type=observe \
  goose run --no-session -t "List the files in this folder and read README.md"
wait
```

Repeat with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` for the
content fixture, update the file names in `test_contract.py`, and run the test.
