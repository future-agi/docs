# Gravitee APIM Gateway to Future AGI (OpenTelemetry traces)

Runnable assets for the page [Send Gravitee APIM Gateway traces to Observe](../../../src/pages/docs/integrations/gateways/gravitee.mdx).
The Gravitee Gateway's built-in OpenTelemetry exporter sends spans for each API call to an OpenTelemetry Collector,
and the Collector forwards them to Future AGI. There is no Gravitee plugin and no traceAI package.

Tested with **graviteeio/apim-gateway 4.12.23** (latest stable tag on Docker Hub, 2026-10-14; the Community
Edition image, no licence), **graviteeio/apim-management-api 4.12.23** (only to create the APIs), **mongo 6.0.8**
(the version Gravitee's own compose file pins) and **otel/opentelemetry-collector-contrib 0.162.0**.

Why a Collector: Future AGI needs the resource attribute `project_name`. Gravitee can add resource attributes
(`extraAttributes`), but its config loader turns every `_` in the key into `.`, so the Gateway exports
`project.name` and Future AGI rejects the batch with HTTP 400. `otelcol.yaml` sets `project_name` instead.

| File | What it is |
| --- | --- |
| `gravitee-opentelemetry.yml` | The `services.opentelemetry` block the page tells customers to put in the Gateway's `gravitee.yml` (verbose off, HTTP/protobuf, no compression, redaction rules) |
| `otelcol.yaml` | The Collector config: bearer-token receiver, sets `project_name`/`project_type`, optional content opt-in, plain protobuf to Future AGI |
| `lib.sh` | Helpers: start/stop MongoDB, Management API, Gateway and Collector in Docker and wait until each is ready; merge the block into the image's own `gravitee.yml` |
| `create_apis.py` | Creates and deploys the test v4 HTTP proxy APIs through the real Management API (per-API tracing switch on/off, verbose on one API) |
| `echo_server.py` | Tiny backend; logs which requests carried a W3C `traceparent` |
| `run_e2e.sh` | The real end-to-end run (below) |
| `check_traces.py` | Checks each trace id the run sent: stored, absent, ERROR, joined to the caller's span |
| `scan_privacy.py` | Greps EVERY stored column of a project (ClickHouse `spans`, Postgres `tracer_*`) for marker strings and secrets |
| `capture_server.py`, `capture_fixtures.sh` | Re-capture the fixtures from a real Gateway (it exports to a local sink instead) |
| `otlp_dump.py` | Prints an OTLP protobuf body as JSON |
| `render_gateway_config.py` | Merges `gravitee-opentelemetry.yml` into a `gravitee.yml` |
| `fixtures/*.pb` | OTLP bodies captured from Gateway 4.12.23: content off, backend down, verbose opt-in, and `extraAttributes` with `project_name` |
| `tests/` | `test_config.py` (the two config files), `test_fixtures.py` (what the Gateway put on the wire), `test_contract.py` (fixtures replayed at a collector), `test_readiness.py` (the readiness waits in `lib.sh`, with fake `docker`/`curl`) |

## Tests

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
pytest tests                 # test_config.py, test_fixtures.py and test_readiness.py need nothing else
export FI_BASE_URL=http://localhost:14338 FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-gravitee-project
pytest tests                 # now also test_contract.py (skips without FI_*)
```

The storage assertions read ClickHouse with `docker exec` (default container `th8103-e2e-clickhouse-1`, override
with `FI_CH_CONTAINER`); they skip if that container is not there.

## Real end-to-end run

Needs Docker (about 1.4 GB for the containers), a reachable Future AGI collector, and the Python packages above.
`LLM_API_KEY` (plus `LLM_BASE_URL`, `LLM_MODEL`) is optional: with it the run also sends a tool-calling chat
completion to an OpenAI-compatible endpoint through a Gravitee API (defaults: `LLM_BASE_URL=http://host.docker.internal:8317`,
a local OpenAI-compatible proxy, and `LLM_MODEL=gpt-6-luna`; set both for your provider).

```bash
export FI_BASE_URL=http://localhost:14338 FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-gravitee-project
export FI_VERIFY=/path/to/fi_verify.py        # optional span-tree check from the local e2e kit
./run_e2e.sh
```

1. A: the Gateway exports straight to Future AGI with `project_name` in `extraAttributes` (expected: HTTP 400, nothing stored)
2. B: content off, the shipped config through the Collector: a normal call (with a caller `traceparent`), a call
   without one (the Gateway starts the trace), a call to an API that has Verbose on, a failing backend, an API with
   tracing off, the optional LLM call, and a call sent right before shutdown
3. C: the opt-in: verbose on the Gateway (`gravitee_services_opentelemetry_verbose=true`) and on the API, first
   with the Collector's `FI_CAPTURE_CONTENT` off, then on; then a wrong Future AGI secret key on the Collector
4. D: a wrong Collector token on the Gateway

It checks every trace id it sent, asserts no key or token appears in the container logs, then scans every stored
column for the unique markers (absent with content off, the verbose header marker present with the opt-in).
Evidence goes to `.evidence/` (not committed). Ports: Gateway 18082, Management API 18083 and the Collector's OTLP
receiver 18084 (loopback only, used for the readiness probe), and the backend on 18090 (all interfaces, so the
containers can reach it); override with `GW_PORT`, `MAPI_PORT`, `OTELCOL_PORT`, `BACKEND_PORT`. Containers are named
`$PREFIX-*` (default `gravitee-fi-e2e`) and removed on exit.

Every start waits for the component's own readiness signal instead of a fixed time:

| Component | Ready when |
| --- | --- |
| MongoDB | `mongosh` in the container gets `ok: 1` for `ping` |
| Management API | `GET /_node/health` on its internal API (inside the container) reports every probe healthy, and the REST API answers 200 |
| Gateway | `GET /_node/health?probes=http-server,sync-process` on its internal API (inside the container) reports both healthy; then the test API `/fi-untraced/` must answer 200: a wrong answer (404, API not deployed) fails after `GW_API_GRACE` seconds (default 30), no answer yet (a slow first request) waits up to `GW_READY_TIMEOUT` |
| Collector | its OTLP/HTTP receiver answers (401 to the unauthenticated probe, so nothing is forwarded) |

Each wait lasts up to `READY_TIMEOUT` seconds (default 600; per component `MONGO_READY_TIMEOUT`, `MAPI_READY_TIMEOUT`,
`GW_READY_TIMEOUT`, `OTELCOL_READY_TIMEOUT`), polled every `READY_POLL` seconds (default 2). If a component is not
ready in time, or its container stops, the run fails and prints the container's last `LOG_TAIL` (default 80) log lines
with key and token values redacted. The time each start took is written to `.evidence/readiness.txt` and printed
before the checks.
