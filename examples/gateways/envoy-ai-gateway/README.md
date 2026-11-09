# Envoy AI Gateway -> Future AGI (TH-8300)

Runnable assets for the page `src/pages/docs/integrations/gateways/envoy-ai-gateway.mdx`.
Tested with `aigw` v1.2.0 (standalone CLI). No Kubernetes files here were applied to a cluster.

| File | What |
| --- | --- |
| `run_aigw.sh` | Starts `aigw` with the documented OTEL env (traces only, HTTP, both key headers, `project_name`, content off unless `FI_CAPTURE_CONTENT=1`) |
| `env.example` | Copy to `.env`, fill in keys |
| `run_e2e.sh` | Real `aigw` -> real Future AGI: default, opt-in, unknown model, bad key, missing project, embeddings; with `LOCAL_STACK=1` also runs `fi_verify.py` and the marker scan |
| `tests/test_recipe_env.py` | Offline: a stub `aigw` proves `run_aigw.sh` exports exactly the documented env |
| `tests/test_contract.py` | Offline: assertions on spans recorded from a real `aigw` v1.2.0 run (`tests/fixtures/`) |
| `tests/record_fixtures.sh` | Re-records the fixtures against a local capture server |
| `tests/scan_local_stack.py` | Scans all stored columns of a local self-hosted stack for a marker |
| `k8s/` | `GatewayConfig` (v1beta1) and Helm values. not yet run on a cluster |

## Run

```bash
python3 -m pytest tests            # offline, no keys, no gateway
cp env.example .env                # fill FI_API_KEY, FI_SECRET_KEY, OPENAI_API_KEY
./run_aigw.sh /path/to/aigw        # gateway on :1975
curl localhost:1975/v1/chat/completions -H 'content-type: application/json' \
  -H 'agent-session-id: s1' -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
```

Get `aigw` from the [envoyproxy/ai-gateway releases](https://github.com/envoyproxy/ai-gateway/releases) (or `go install github.com/envoyproxy/ai-gateway/cmd/aigw@v1.2.0`).
