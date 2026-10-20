# Claude Managed Agents (TH-8267)

Docs page: `src/pages/docs/integrations/claude-managed-agents.mdx`. The integration is an OpenTelemetry Collector
(`otelcol.yaml`) between a Claude Console telemetry destination and Future AGI.

Everything here is a **stand-in** for Anthropic: no Anthropic account, destination, API key, model call or spend.
Payloads are built from Anthropic's published span reference. A live run is blocked on an Anthropic Console org admin
plus an API key with Managed Agents access and billing.

| File | Purpose |
| --- | --- |
| `otelcol.yaml` | The recipe the page embeds (a test keeps them identical): bearer auth, gzip accepted, `project_name` stamped, span kinds and session id mapped, content gated off by default. |
| `spike/fixture.py` | Builds an OTLP protobuf payload shaped like the Managed Agents API spans in Anthropic's span reference (made-up values). |
| `spike/deliver.py` | Sends a payload the way Anthropic's delivery rules describe: gzip first, uncompressed resend on 400 or 415, `User-Agent: Claude-Platform`, only the destination's headers. |
| `spike/run_collector_spike.py` | Delivers one scenario (metadata, content, error, duplicate, badtoken) to the collector. |
| `run_collector_e2e.sh` | Starts the collector in Docker, runs all scenarios into a local Future AGI, then verifies (optional `VERIFY=fi_verify.py`). |
| `tools/scan_local_stack.py` | Scans every stored row of a project for markers (privacy check). |
| `run_e2e.sh`, `spike/run_fixture_spike.py`, `spike/sdk_app.py`, `spike/sessions_stub.py` | The 2026-10-16 spikes: payload straight into Future AGI (rejected without `project_name`), and the real `anthropic` SDK against a Sessions API stub. |
| `tests/` | `test_page_claims.py` (page, recipe, fixture agree), `test_fixture_and_delivery.py`, `test_sdk_tracing_stub.py`. All offline. |

```bash
pip install -r requirements.txt pyyaml
python -I tests/test_page_claims.py
python -I tests/test_fixture_and_delivery.py
python -I tests/test_sdk_tracing_stub.py
# collector run, needs Docker and a local Future AGI collector:
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 PYTHON=$(which python) bash run_collector_e2e.sh
```
