# Cloudflare AI Gateway tracing: examples and tests

Runnable assets behind the page
[Cloudflare AI Gateway tracing with Future AGI](../../../src/pages/docs/integrations/gateways/cloudflare-ai-gateway.mdx).

Cloudflare does not run here. One stand-in takes its place and is named as such in every file:

| Stand-in | What it replaces | Why |
| --- | --- | --- |
| `standin_cloudflare.py` with `gateway_fixture.py` | The OpenTelemetry exporter of a Cloudflare AI Gateway, the sending side only | A real run needs a Cloudflare account, a gateway, and a public HTTPS endpoint for Cloudflare's network to reach. The stand-in posts OTLP built from the attribute names Cloudflare publishes (link in `gateway_fixture.py`) and takes the Headers field as a JSON object. With `--live` the prompt, completion and token counts come from a real model call. |

What is real: the OpenTelemetry Collector container (`otelcol.yaml`), the Future AGI collector and storage you point it at, and the model calls behind `--live`.

Nothing in `gateway_fixture.py` was captured from Cloudflare. Where Cloudflare's page leaves something open, the file says `ASSUMED` or `SYNTHETIC`: the span name, kind, scope and resource attributes, the shape of the prompt and completion JSON, how a failure is expressed, and the cost value.

## Files

| Path | What it is |
| --- | --- |
| `otelcol.yaml` | The collector recipe from the page |
| `standin_cloudflare.py` | The stand-in sender: `send` (one gateway span) and `caller` (the application's parent span for a linked trace) |
| `gateway_fixture.py` | The OTLP request builder (JSON and protobuf), with the source of every attribute |
| `tools/wire_tap.py` | Records what the collector exports to Future AGI, then forwards it unchanged |
| `tools/scan_local_stack.py` | Counts needles across every stored row of a project (all ClickHouse and Postgres tables with a `project_id`) and across wire-tap files |
| `run_e2e.sh` | Runs all of it against a self-hosted Future AGI |
| `tests/` | Unit tests plus a contract test against a running Future AGI collector |

## Run the tests

Python 3.10 or newer.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
pytest tests -q
```

`tests/test_contract_local_collector.py` is skipped unless `FI_API_KEY`, `FI_SECRET_KEY` and `FI_BASE_URL` (for example `http://localhost:14338`) are set. It asserts: a Cloudflare-shaped batch without `project_name` is rejected with 400; the same batch with it is accepted as JSON and as protobuf; wrong keys and a Bearer header are 401; gzip is 400.

## Try the stand-in by hand

```bash
export EXPORT_AUTH="Bearer $GATEWAY_TOKEN"        # the secret the collector expects
python standin_cloudflare.py send --endpoint http://localhost:4318/v1/traces --header Authorization=EXPORT_AUTH
```

`--headers '{"Authorization": "Bearer ..."}'` takes the JSON object the way Cloudflare's Headers field does. `--header NAME=ENVVAR` reads a value from the environment so it stays out of your shell history. `--content-type protobuf`, `--gzip`, `--scenario success|error|no-usage|no-prompt`, `--otel-trace-id` and `--otel-parent-span-id` (what the caller sent in the `cf-aig-otel-*` headers). `--live` makes a real model call first (`STANDIN_UPSTREAM_BASE_URL`, `STANDIN_UPSTREAM_API_KEY`, `STANDIN_MODEL`).

## Run the end-to-end script

It needs Docker, a self-hosted Future AGI in Docker (the scan reads its Postgres and ClickHouse containers; set `FI_PG_CONTAINER` and `FI_CH_CONTAINER` if yours are named differently, or `SKIP_SCAN=1`), and any OpenAI-compatible endpoint for `--live`.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338
export STANDIN_UPSTREAM_BASE_URL=http://127.0.0.1:8317/v1 STANDIN_UPSTREAM_API_KEY=... STANDIN_MODEL=gpt-6-luna
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all
```

`direct` runs the exporter straight at Future AGI, `collector` runs the recipe, `all` runs both. Evidence (wire-tap files, scan results, verify output, collector logs) goes to `./evidence`. Those files can hold prompts: keep them out of git. The script starts one collector container named `th8103-rest-cloudflare-ai-gateway-otelcol` (`--memory 512m`) at a time and removes it on exit.

| Mode | Cases |
| --- | --- |
| `direct` | Right keys without `project_name`, wrong keys, Bearer, no headers; JSON and protobuf with `project_name`; gzip; the `/tracer/v1/traces` path; a span with no prompt |
| `collector` | No token and a wrong token; real model calls as JSON and protobuf; a failed request with a synthetic exception event; missing usage, missing prompt, gzip; a gateway span linked to an application trace; then the content-on opt-in, and wrong Future AGI keys behind a collector that still accepts the gateway's token; secrets searched for in every log |

## Not verified

Cloudflare's real payload and span tree, the dashboard Headers field with a Bearer value, whether Cloudflare compresses or retries exports, how a failed request is marked in OTLP, the cost value, TLS in front of the collector, a collector reachable from the internet, and the hosted Future AGI URL (`api.futureagi.com`).
