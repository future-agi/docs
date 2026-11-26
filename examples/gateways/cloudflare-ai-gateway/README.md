# Cloudflare AI Gateway tracing: examples and tests

Runnable assets behind the page
[Cloudflare AI Gateway tracing with Future AGI](../../../src/pages/docs/integrations/gateways/cloudflare-ai-gateway.mdx).

## Live vendor verification (2026-10-18)

A real Cloudflare AI Gateway (OpenAI `gpt-4o-mini` behind it), configured through the Cloudflare API with `Authorization: Bearer <token>` in the exporter's Headers, exported to this collector running on Google Cloud Run (HTTPS), which forwarded to Future AGI cloud. `tests/fixtures/cloudflare-2026-10-18-*.json` are two of those exports as Cloudflare sent them (the prompts are synthetic marker text): one chat completion and one streamed completion. What the run showed, and what it did not cover, is on the page under "Live vendor verification".

The real export differs from Cloudflare's page: span `cf.aig.request` (kind internal, scope `ai`, resource `service.name=ai-gateway`), `gen_ai.provider.name` instead of `gen_ai.model.provider`, and the request and response bodies in `gen_ai.input.messages` and `gen_ai.output.messages` instead of `gen_ai.prompt_json` and `gen_ai.completion_json`. `otelcol.yaml` handles both spellings. Failed provider requests and cache hits exported no span.

## Running without Cloudflare

`standin_cloudflare.py` with `gateway_fixture.py` posts the same span shape from your machine, so you can try the collector without a Cloudflare account. It takes the Headers field as a JSON object, and with `--live` the prompt, completion and token counts come from a real model call. `--doc-names` posts the names on Cloudflare's page instead. Two things in it are `SYNTHETIC`: the cost value, and the `error` scenario (the real gateway exported nothing for a failed request; the scenario stays to test the collector's error-text rule).

## Files

| Path | What it is |
| --- | --- |
| `otelcol.yaml` | The collector recipe from the page |
| `standin_cloudflare.py` | The stand-in sender: `send` (one gateway span) and `caller` (the application's parent span for a linked trace) |
| `gateway_fixture.py` | The OTLP request builder (JSON and protobuf), in the shape the real gateway sent |
| `tests/fixtures/` | Two exports captured from a real gateway on 2026-10-18 |
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

`tests/test_real_payload_collector.py` posts the captured real payloads (JSON and protobuf) to `otel/opentelemetry-collector-contrib:0.162.0` running `otelcol.yaml` in Docker and checks what it forwards, with content off and on. It is skipped without Docker or the image, or with `CFAIG_SKIP_DOCKER=1`.

`tests/test_contract_local_collector.py` is skipped unless `FI_API_KEY`, `FI_SECRET_KEY` and `FI_BASE_URL` (for example `http://localhost:14338`) are set. It asserts: a Cloudflare-shaped batch without `project_name` is rejected with 400; the same batch with it is accepted as JSON and as protobuf; wrong keys and a Bearer header are 401; gzip is 400 on self-hosted Future AGI before v1.56.0 and accepted from v1.56.0. The test defaults to expecting HTTP 200; set `FI_EXPECT_GZIP_STATUS=400` only for an older self-hosted receiver.

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

`direct` runs the stand-in exporter straight at Future AGI, `collector` runs the recipe with the stand-in, `replay` posts the captured real payloads through the recipe (content off, then on), `all` runs the three. Evidence (wire-tap files, scan results, verify output, collector logs) goes to `./evidence`. Those files can hold prompts: keep them out of git. The script starts one collector container named `th8103-rest-cloudflare-ai-gateway-otelcol` (`--memory 512m`, change with `OTELCOL_CONTAINER`, ports with `RECV_PORT` and `TAP_PORT`) at a time and removes it on exit.

| Mode | Cases |
| --- | --- |
| `direct` | Right keys without `project_name`, wrong keys, Bearer, no headers; JSON and protobuf with `project_name`; gzip; the `/tracer/v1/traces` path; a span with no prompt |
| `collector` | No token and a wrong token; real model calls as JSON and protobuf; a failed request with a synthetic exception event; missing usage, missing prompt, gzip; a gateway span linked to an application trace; then the content-on opt-in, and wrong Future AGI keys behind a collector that still accepts the gateway's token; secrets searched for in every log |
| `replay` | The captured real payloads with content off (stored as `llm`, no request or response text in any stored row, metadata kept), then with content on (Input and Output panes filled) |

## Not covered

The dashboard form itself (the live run set the same fields through the API), the exporter's Authorization field with a Secrets Store reference, whether Cloudflare retries an export that fails with a 5xx or a timeout (a 401 was not retried), providers other than OpenAI, Workers AI, custom providers, and TLS you terminate yourself.
