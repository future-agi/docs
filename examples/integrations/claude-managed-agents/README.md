# Claude Managed Agents (TH-8267)

Tracing Claude Managed Agents is **not supported yet**. See `DECISION.md` and the docs page
`src/pages/docs/integrations/claude-managed-agents.mdx`.

Everything here is a **stand-in** spike. No Anthropic account, API key, model call or spend was used, and
nothing here is a relay or a collector config: nothing listens for Anthropic's servers.

| File | Purpose |
| --- | --- |
| `spike/fixture.py` | Builds an OTLP protobuf payload shaped like the Managed Agents API spans in Anthropic's span reference (made-up values). `add_project_name()` is the one change a collector in front of Future AGI would have to make. |
| `spike/deliver.py` | Sends a payload the way Anthropic's delivery rules describe: gzip first, uncompressed resend on 400 or 415, `User-Agent: Claude-Platform`, only the destination's headers. |
| `spike/run_fixture_spike.py` | Spike A: as-is delivery (rejected), with `project_name` (accepted), content mode, failure. |
| `spike/sessions_stub.py` | Local stand-in for the Sessions API, with a scripted agent that calls one custom tool. |
| `spike/sdk_app.py` | Spike B: the real `anthropic` SDK with its built-in tracing, exported by the app straight to Future AGI. |
| `run_e2e.sh` | Runs both spikes against a local Future AGI in a throwaway venv. |
| `tests/` | `test_fixture_and_delivery.py` (payload shape, delivery rules), `test_sdk_tracing_stub.py` (SDK spans in memory), `test_page_claims.py` (page vs `fixtures/observed.json`). All offline. |

```bash
pip install -r requirements.txt
python -I tests/test_fixture_and_delivery.py
python -I tests/test_sdk_tracing_stub.py
python3 -I tests/test_page_claims.py
# spike, needs a local Future AGI collector:
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:14338 bash run_e2e.sh
```
