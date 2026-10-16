# Azure API Management / AI Gateway tier tracing for Future AGI (TH-8298)

Runnable assets for `docs/integrations/gateways/azure-apim`. **Nothing here touches Azure.** Read the page first.

| File | What it is |
| --- | --- |
| `policy/otlp-egress.policy.xml` | Variant A: the APIM policy (`set-backend-service`, `rewrite-uri`, `set-header`). Never deployed. |
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

Variant A (needs an APIM instance, any tier; Developer is the non-production one, and it is billed):
- the policy XML deploys and forwards: `set-backend-service` + `rewrite-uri` produce `/tracer/v1/traces`;
- APIM does not log or rewrite `X-Api-Key`/`X-Secret-Key`, and passes the request body and `Content-Encoding` through unchanged;
- request-size limits against a large batch, and the hosted `https://api.futureagi.com/tracer/v1/traces` backend.

Variant B (needs an AI Gateway tier instance: preview, East US 2 or Sweden Central, pricing not announced):
- the Monitoring destination form: whether it sends a custom header or only an access token, and whether it takes the full traces URL;
- the real trace: span names, attribute names (policy, API key, cost), whether it carries prompt text, whether it compresses, trace-context propagation from the client;
- that Observe shows the typed spans, and that the content filter covers the real attribute names (send a unique string in a prompt and search).

The attribute names in `gateway_trace.py` other than `gen_ai.*` and `azure.ai_gateway.identity.claims.*` are invented placeholders.
