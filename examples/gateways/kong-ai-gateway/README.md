# Kong AI Gateway to Future AGI (OpenTelemetry plugin)

Runnable assets for the page [Send Kong AI Gateway traces to Observe](../../../src/pages/docs/integrations/gateways/kong-ai-gateway.mdx).
Kong's own `opentelemetry` plugin exports the spans the `ai-proxy` plugin creates, straight to Future AGI over
OTLP/HTTP protobuf. There is no custom Kong plugin and no traceAI package.

Tested with **kong/kong-gateway 3.16.0.1** (latest tag on Docker Hub on 2026-10-16); the span shape was also checked on
3.14.0.16. Open-source `kong:3.9.4` was run too and emits no Gen AI spans.

| File | What it is |
| --- | --- |
| `kong.yml` | The declarative config the page tells customers to use (`ai-proxy` + `opentelemetry`, `${...}` placeholders) |
| `lib.sh` | Helpers: start/stop Kong in Docker (768 MB cap), render the config with `envsubst`, send a chat request |
| `run_e2e.sh` | The real end-to-end run (below) |
| `scan_privacy.py` | Greps EVERY stored column of a project (ClickHouse `spans`, Postgres `tracer_*`) for marker strings |
| `capture_server.py`, `capture_fixtures.sh` | Re-capture the fixtures from a real Kong (Kong exports to a local sink instead of Future AGI) |
| `fixtures/*.pb` | OTLP protobuf bodies captured from a real Kong 3.16.0.1: statistics only, and with payloads |
| `tests/` | `test_contract.py` replays the fixtures at a collector; `test_config.py` checks `kong.yml`; `test_readiness.py` checks the readiness wait in `lib.sh` with fake `docker`/`curl` |

## Tests

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
export FI_BASE_URL=http://localhost:14338 FI_API_KEY=... FI_SECRET_KEY=... FI_PROJECT_NAME=my-kong-project
pytest tests            # test_config.py and test_readiness.py need nothing; test_contract.py needs a collector (skips if FI_* unset)
```

The storage assertions read ClickHouse with `docker exec` (default container `th8103-e2e-clickhouse-1`, override with
`FI_CH_CONTAINER`); they skip if that container is not there.

## Real end-to-end run

Needs Docker, a reachable Future AGI collector, an OpenAI-compatible upstream (`UPSTREAM_API_KEY`, optionally
`UPSTREAM_CHAT_URL` and `UPSTREAM_MODEL`) and `envsubst`. It boots the real Kong four times:

1. content off (`log_payloads: false`), plus a tool-calling request, a streaming request and a request with a query string
2. content on (`log_payloads: true`)
3. failure case: upstream unreachable
4. Future AGI keys given as Kong vault references (`{vault://env/...}`)

```bash
export FI_BASE_URL=http://localhost:14338 FI_API_KEY=... FI_SECRET_KEY=... UPSTREAM_API_KEY=...
export FI_VERIFY=/path/to/fi_verify.py        # optional span-tree check from the local e2e kit
./run_e2e.sh
```

It prints the trace ids it sent, asserts no secret value appears in Kong's logs, then scans every stored column for the
unique content marker (absent with content off, present with content on). Evidence goes to `.evidence/` (not committed).
Kong runs on host ports 18010 (proxy), 18011 (admin) and 18012 (Status API), the last two on loopback only; change
with `KONG_PROXY_PORT` / `KONG_ADMIN_PORT` / `KONG_STATUS_PORT`. Containers are removed on exit.

Each boot waits for Kong's readiness endpoint, `GET /status/ready` on the Status API, which returns 503 until the
declarative config is loaded and the router and plugins are built, then 200. The wait is up to `KONG_READY_TIMEOUT`
seconds (default 300, polled every `KONG_READY_POLL` seconds). If Kong is not ready in time, or its container stops,
the run fails and prints the last `KONG_LOG_TAIL` (default 60) lines of Kong's log with the key values redacted. The
time each boot took to become ready is written to `.evidence/readiness.txt`.

The run ends with `E2E PASS`. A failed readiness wait, a privacy scan failure, or `fi_verify` still failing after six
tries stops it with a non-zero exit.
