# Azure API Management / AI Gateway tier tracing for Future AGI (TH-8298)

Runnable assets for `docs/integrations/gateways/azure-apim`. **The scripts and tests here never contact Azure.** Variant A's policy was deployed unchanged on a real APIM Consumption instance on 2026-10-19 (see "Live vendor verification" on the page); variant B was not run against Azure. Read the page first.

| File | What it is |
| --- | --- |
| `policy/otlp-egress.policy.xml` | Variant A: the APIM policy (`set-backend-service`, `rewrite-uri`, `set-header`). Deployed unchanged on a Consumption-tier instance on 2026-10-19. |
| `apim_standin.py` | **STAND-IN for APIM.** Models that policy locally so the real client and collector can be exercised. |
| `app.py` | Variant A client: real `traceAI-openai`, no Future AGI keys, exports through the APIM URL. |
| `otelcol.yaml` | Variant B: OpenTelemetry Collector config between the AI Gateway tier and Future AGI. |
| `gateway_trace.py` | **SYNTHETIC** AI Gateway-shaped OTLP trace (and the negative-case poster). Not captured from Azure. |
| `run_e2e.sh` | The end-to-end run: `./run_e2e.sh [a\|b\|all]`. Needs a self-hosted Future AGI; see the header. |
| `tools/scan_local_stack.py` | Scans every stored column of a project for a marker (privacy proof). Read-only. |
| `tests/` | Offline tests (no Future AGI, no Docker): `pytest`. |

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
```

## What a live run on Azure still has to confirm

Variant A. Confirmed live on 2026-10-19 (Consumption tier, East US, hosted `https://api.futureagi.com/tracer/v1/traces` backend): the policy XML deploys unchanged and forwards (`set-backend-service` + `rewrite-uri` produce `/tracer/v1/traces`); `401` without the subscription key, `404` for other paths, `400` for a batch without `project_name` and for a gzip body, `200` for an empty export. Still open:
- APIM header and payload logging (left off in the live run): whether turning it on records `X-Api-Key`/`X-Secret-Key` or the request body;
- request-size limits against a large batch;
- other tiers (Developer, Basic, Standard, Premium, v2 tiers);
- a stored-column scan of the hosted project (the live trace was read back through the hosted API only).

Variant B (needs an AI Gateway tier instance: preview, East US 2 or Sweden Central, pricing not announced):
- the Monitoring destination form: whether it sends a custom header or only an access token, and whether it takes the full traces URL;
- the real trace: span names, attribute names (policy, API key, cost), whether it carries prompt text, whether it compresses, trace-context propagation from the client;
- that Observe shows the typed spans, and that the content filter covers the real attribute names (send a unique string in a prompt and search).

The attribute names in `gateway_trace.py` other than `gen_ai.*` and `azure.ai_gateway.identity.claims.*` are invented placeholders.
