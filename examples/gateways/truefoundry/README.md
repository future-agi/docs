# TrueFoundry AI Gateway tracing: examples and tests

Runnable assets behind the page
[TrueFoundry AI Gateway tracing with Future AGI](../../../src/pages/docs/integrations/gateways/truefoundry.mdx).

No TrueFoundry code runs here. Two stand-ins take its place and are named as such in every file:

| Stand-in | What it replaces | Why |
| --- | --- | --- |
| `standin_gateway.py` | The gateway a client calls | A real gateway needs a TrueFoundry account. The stand-in serves only what TrueFoundry's docs describe: `POST /chat/completions` at the root, `provider_account/model_name` ids, a Bearer token, 403 for a model the caller may not use. It forwards everything else to any OpenAI-compatible endpoint. |
| `native/tfy_batch.py` | The gateway's OTEL exporter | Builds OTLP batches from the attribute names in TrueFoundry's docs. They are not captured from a gateway. `native/post_batch.py` sends them. |

What is real: `traceai-openai`, the `openai` client, the OpenTelemetry Collector container, and the Future AGI collector and storage you point them at.

## Files

| Path | What it is |
| --- | --- |
| `client_example.py` | The client-tracing recipe: `register()`, `OpenAIInstrumentor`, an OpenAI client on the gateway base URL, an agent with one tool call |
| `standin_gateway.py` | Stand-in gateway (see above) |
| `native/tfy_batch.py`, `native/post_batch.py` | Synthetic TrueFoundry-shaped batches and a poster (HTTP proto or JSON, gzip, gRPC, five auth modes) |
| `native/otelcol.yaml` | The OpenTelemetry Collector recipe from the page |
| `tools/wire_tap.py` | Records what an OTLP/HTTP exporter sent, then forwards it unchanged |
| `tools/scan_local_stack.py` | Counts needles across every stored row of a project and across wire-tap files |
| `run_e2e.sh` | Runs all of it against a self-hosted Future AGI |
| `tests/` | Unit tests, no network, no Docker |

## Run the tests

Python 3.10 to 3.13 (`traceai-openai` does not support 3.14).

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
pytest tests -q
```

## Run the client example against your own gateway

```bash
export FI_API_KEY=... FI_SECRET_KEY=...        # Future AGI
export FI_BASE_URL=http://localhost:14338       # self-hosted only
export TFY_API_KEY=...                          # TrueFoundry PAT or VAT
export TFY_MODEL=openai-main/gpt-4o-mini        # provider_account/model_name
python client_example.py
```

`TFY_BASE_URL` defaults to `https://gateway.truefoundry.ai`. For a self-hosted gateway copy the base URL from the Playground Code Snippets.

## Run the end-to-end script

It needs a self-hosted Future AGI in Docker (the scan reads its Postgres and ClickHouse containers; set `FI_PG_CONTAINER` and `FI_CH_CONTAINER` if yours are named differently, or `SKIP_SCAN=1`), and any OpenAI-compatible endpoint for the stand-in to forward to.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338
export STANDIN_UPSTREAM_BASE_URL=http://127.0.0.1:8317/v1 STANDIN_UPSTREAM_API_KEY=... STANDIN_MODEL=gpt-6-luna
export FI_GRPC_TARGET=localhost:14337           # optional, adds the gRPC cases
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all
```

`client`, `native` and `collector` run one part each. Evidence (wire-tap files, scan results, verify output) goes to `./evidence`. Those files can hold prompts: keep them out of git.

| Mode | Cases |
| --- | --- |
| `client` | success with a tool call, failure (403), content off with unique markers, content on, failure with content off |
| `native` | no `project_name` (400), documented setup, gateway flag off, failure with and without an OTLP error status, Basic, Bearer, wrong keys, no credentials, gzip, JSON, the `/tracer/v1/traces` path, gRPC |
| `collector` | collector 0.162.0 in Docker (`--memory 512m`, removed on exit): project and keys added, content, identity and error text removed, ERROR status kept, gzip in, gRPC in |

## What was observed

See the page for the tables. In short, on the local stack tested:

- Client path: agent, LLM, tool, LLM hierarchy; model and tokens from the response; failure as `ERROR`.
- Content off: no marker, user name, host name or path in the exporter's output or in any stored column. A failed call still exports the error text, and on the wire a stack trace.
- Gateway export, synthetic: the collector rejects a batch without `project_name` (400), accepts two header pairs or one Basic header, rejects Bearer (401) and gzip (400), and takes a 15 MiB request but not a 17 MiB one (413).
- Model and tokens appear only when the batch carries the `gen_ai.*` attributes, which TrueFoundry writes only with `ENABLE_GEN_AI_OTEL_ATTRIBUTES=true`.
- The collector recipe removed every content, identity and error-text attribute it lists.

## Not verified

A real TrueFoundry gateway, TrueFoundry's OTEL Config screen, whether its exporter compresses, the real attribute placement and values, what the hosted gateway lets you set, Future AGI cloud (`api.futureagi.com`) with a TrueFoundry batch, and streaming.
