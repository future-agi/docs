# OpenRouter Broadcast tracing: examples and tests

Runnable assets behind the page
[OpenRouter Broadcast tracing with Future AGI](../../../src/pages/docs/integrations/gateways/openrouter-broadcast.mdx).

OpenRouter does not run here. One stand-in takes its place and is named as such in every file:

| Stand-in | What it replaces | Why |
| --- | --- | --- |
| `standin_openrouter.py` with `broadcast_fixture.py` | OpenRouter Broadcast's OpenTelemetry Collector destination, the sending side only | A real run needs an OpenRouter account and a public HTTPS endpoint for OpenRouter's cloud to reach. The stand-in posts OTLP/JSON built from the attribute keys OpenRouter publishes (links in `broadcast_fixture.py`), sends the Test Connection probe the way the Webhook page describes it, and takes the Headers field as a JSON object. With `--live` the prompt, completion, tool call and token counts come from real model calls. |

What is real: the OpenTelemetry Collector container (`otelcol.yaml`), the Future AGI collector and storage you point it at, and the model calls behind `--live`.

Live check, 2026-10-19: real OpenRouter Broadcast traffic was captured on Cloud Run and replayed through `otelcol.yaml`; see the page's "Live vendor verification" section. `broadcast_fixture.py` itself was written from OpenRouter's documentation, before that run, and differs from the real payload (no separate root span, `gen_ai.usage.total_cost`, `span.status_message`). Where OpenRouter's pages leave something open, the file says `ASSUMED` or `SYNTHETIC`: the span tree, the shape of the prompt and completion strings, how a failure is expressed in OTLP, and the exception event used to exercise the privacy rule. No cost attribute is written, because OpenRouter does not publish its key.

## Files

| Path | What it is |
| --- | --- |
| `otelcol.yaml` | The collector recipe from the page |
| `standin_openrouter.py` | The stand-in sender: `probe` (Test Connection) and `send` |
| `broadcast_fixture.py` | The OTLP/JSON request builder, with the sources of every key |
| `tools/wire_tap.py` | Records what the collector exports to Future AGI, then forwards it unchanged |
| `tools/scan_local_stack.py` | Counts needles across every stored row of a project (all ClickHouse and Postgres tables with a `project_id`) and across wire-tap files |
| `tools/second_workspace.py` | Local test stack only: makes a second workspace and key to check workspace isolation, then removes them |
| `run_e2e.sh` | Runs all of it against a self-hosted Future AGI |
| `tests/` | Unit tests, no network beyond loopback, no Docker |

## Run the tests

Python 3.10 or newer.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
pytest tests -q
```

## Try the stand-in by hand

```bash
export BROADCAST_AUTH="Bearer $BROADCAST_TOKEN"        # the secret the collector expects
python standin_openrouter.py probe --endpoint http://localhost:4318/v1/traces --header Authorization=BROADCAST_AUTH
python standin_openrouter.py send  --endpoint http://localhost:4318/v1/traces --header Authorization=BROADCAST_AUTH --scenario success
```

`--headers '{"Authorization": "Bearer ..."}'` takes the JSON object the way OpenRouter's Headers field does. `--header NAME=ENVVAR` reads a value from the environment so it stays out of your shell history. Scenarios: `success`, `privacy` (OpenRouter's Privacy Mode on), `error`, `nested`, `legacy` (the `prompt_tokens` spelling), `no-usage`. `--live` makes real model calls first (`STANDIN_UPSTREAM_BASE_URL`, `STANDIN_UPSTREAM_API_KEY`, `STANDIN_MODEL`).

## Run the end-to-end script

It needs Docker, a self-hosted Future AGI in Docker (the scan reads its Postgres and ClickHouse containers; set `FI_PG_CONTAINER` and `FI_CH_CONTAINER` if yours are named differently, or `SKIP_SCAN=1`), and any OpenAI-compatible endpoint for `--live`.

```bash
export FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338
export STANDIN_UPSTREAM_BASE_URL=http://127.0.0.1:8317/v1 STANDIN_UPSTREAM_API_KEY=... STANDIN_MODEL=gpt-6-luna
PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh all
```

`direct` runs the destination straight at Future AGI, `collector` runs the recipe, `all` runs both. Evidence (wire-tap files, scan results, verify output, collector logs) goes to `./evidence`. Those files can hold prompts: keep them out of git. The script starts one collector container named `th8103-rest-openrouter-broadcast-otelcol` (`--memory 512m`) at a time and removes it on exit. `SKIP_CROSS_WS=1` skips the second-workspace check, which writes rows into the stack's Postgres and soft-deletes them afterwards.

| Mode | Cases |
| --- | --- |
| `direct` | Test Connection with right keys, wrong keys, Bearer and no headers; a generation with and without `project_name`; gzip; the `/tracer/v1/traces` path; the same body twice; an oversized body; a second workspace's key |
| `collector` | Test Connection with no token, a wrong token and the right token; two real model calls; a failed request with a synthetic exception event; OpenRouter Privacy Mode; both token spellings and no usage; gzip; a nested trace; then the content-on opt-in, an oversized generation, and wrong Future AGI keys behind a collector whose Test Connection still passes; secrets searched for in every log |

## Not covered

Provider fallback, tool calls, cancelled generations, Privacy Mode in OpenRouter, `trace_id` and `parent_span_id` linking, TLS in front of a collector you run yourself.
