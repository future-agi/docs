# LiteLLM Proxy to Future AGI (OpenTelemetry)

Runnable assets for the page [LiteLLM Proxy tracing](../../../src/pages/docs/integrations/gateways/litellm-proxy.mdx).
LiteLLM Proxy's own OpenTelemetry callback sends spans straight to Future AGI. There is no Future AGI
package in the proxy and `traceAI-litellm` is not involved: that package traces the LiteLLM Python SDK
inside your application, a different process.

Tested with LiteLLM Proxy **1.105.1** (the official `ghcr.io/berriai/litellm:v1.105.1` image and a
`pip install` on Python 3.12). Nothing here calls a paid model: the default upstream is a mock.

| File | What it is |
| --- | --- |
| `config.yaml` | Proxy config: one model, `callbacks: ["otel"]`, master key from the environment |
| `env.example` | The environment a customer sets (endpoint, two key headers, `project_name`, content capture) |
| `requirements.txt` | Tested pip pins (`litellm[proxy]` alone does **not** install the OpenTelemetry SDK or exporter) |
| `mock_upstream.py` | OpenAI-compatible mock (plain, streaming, tool calls, HTTP 500). Stdlib only |
| `send_requests.py` | Sends plain, stream, tool, error, unreachable, joined (`traceparent`), headers and bad-key requests |
| `otlp_sink.py` | Records what an OTLP/HTTP exporter really sends (path, compression, which auth headers, decoded spans) |
| `otlp_contract.py` | Checks an export against the Future AGI ingest contract (also used by the tests) |
| `collector/otelcol-scrub.yaml` | Optional OpenTelemetry Collector config that removes error text, stack traces and addresses (written and tested for the v2 callback only) |
| `make_fixture.py` | Turns a sink capture into a committed test fixture |
| `run_e2e.sh` | Starts the mock, a sink (or Future AGI as target), the proxy; sends requests; checks the export |
| `tests/` | Unit and contract tests (`test_assets.py` also checks the config files and the docs page); `tests/fixtures/` are real exports from 1.105.1 |

## Run the tests

Python 3.9 or newer, standard library only:

```bash
cd examples/gateways/litellm-proxy
python3 -m unittest discover -s tests -t .
```

## Run the proxy for real

Needs Docker (or `RUNNER=pip` with Python 3.10 to 3.14). No keys:

```bash
./run_e2e.sh                      # v2 callback, content off, mock upstream, local sink: prints PASS/FAIL lines
CONTENT=on ./run_e2e.sh           # SPAN_ONLY: the marker must now be present
MODE=v1 ./run_e2e.sh              # the legacy callback
COLLECTOR=scrub ./run_e2e.sh      # through collector/otelcol-scrub.yaml
NO_PROJECT=1 ./run_e2e.sh         # no project_name: the check fails, as Future AGI would reject the batch
```

The first Docker start can take minutes on a busy machine; `START_TIMEOUT` (seconds) controls the wait.

Send the same traffic to your own Future AGI. Use the traces URL of your deployment as `FI_BASE_URL`
(self-hosted collectors serve `/v1/traces`; `FI_TRACES_PATH` overrides the path):

```bash
TARGET=futureagi FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
  FI_PROJECT_NAME=litellm-proxy-e2e ./run_e2e.sh
```

Use a real model instead of the mock with `UPSTREAM=real UPSTREAM_MODEL=openai/<model> UPSTREAM_API_BASE=... UPSTREAM_API_KEY=...`.
That spends whatever your provider charges.

`run_e2e.sh --help` lists every setting. It removes the containers it starts.

## Regenerate a fixture

```bash
OUT=$PWD/out/capture MARKER=MARK_example ./run_e2e.sh
python3 make_fixture.py out/capture/captures my-fixture --mode v2 --content off --marker MARK_example \
  --version 1.105.1 --runner docker --scenarios-file out/capture/scenarios.jsonl
```

Fixtures hold no keys: the proxy exports a hash of the API key, never the key, and the tests check that
nothing shaped like `sk-...` is in any attribute.
