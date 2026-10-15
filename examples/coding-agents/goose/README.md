# goose application session tracing

goose has a built-in OpenTelemetry exporter. This folder holds the settings
that point it at Future AGI, a script that runs one real session with them,
and a contract test built from a recorded goose 1.54.0 export.

Docs page: `src/pages/docs/integrations/coding-agents/goose.mdx`.

| File | What it is |
| --- | --- |
| `futureagi-otel.env` | The recipe: OTLP endpoint, headers, project resource attributes, traces only, content off. |
| `run_e2e.sh` | Runs one `goose run` with the recipe in a throwaway folder and prints a marker string to search for. Needs a configured goose and `FI_API_KEY` / `FI_SECRET_KEY`. |
| `record_otlp.py` | Loopback OTLP/HTTP receiver. Decodes what goose sends and writes span names, parents, and attribute keys, with values dropped except for a structural allowlist. |
| `fixtures/goose-1.54.0-default.json` | Recorded from a real goose 1.54.0 run with the recipe (content off). |
| `fixtures/goose-1.54.0-content.json` | Same run with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. Values are still dropped; only the keys show content was exported. |
| `fixtures/goose-1.54.0-anthropic.json` | Same prompt with goose's Anthropic provider (content off): the tree is the same, only `gen_ai.provider.name` and the model change. |
| `test_contract.py`, `run_contract.sh` | Offline test of the span tree and the privacy default against the fixtures. |

## Run the contract test

```bash
./run_contract.sh                      # stdlib only
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
