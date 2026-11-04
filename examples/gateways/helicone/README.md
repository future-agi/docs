# Trace Helicone gateway calls with Future AGI

Run the Python or TypeScript example against a self-hosted Helicone AI Gateway and view the client call in Future AGI **Observe**. The examples use the published traceAI OpenAI instrumentors; you do not need a Helicone tracing package or a separate receiver. See the [Helicone integration guide](../../../src/pages/docs/integrations/gateways/helicone.mdx) for the minimal application snippets.

This setup uses Helicone AI Gateway 0.2.0-beta.30 at its `/ai` route with an OpenAI-compatible upstream. It does not cover hosted Helicone or the classic proxy.

## Set up the gateway and collector

Configure your upstream provider and model using the [Helicone AI Gateway instructions](https://github.com/Helicone/ai-gateway/tree/v0.2.0-beta.30). The commands below assume the gateway listens at `http://localhost:8080/ai`, gateway authentication is disabled **only on your trusted local machine**, and the configured model is `openai/gpt-4o-mini`. Do not expose an unauthenticated gateway to the internet. Keep upstream provider credentials on the gateway.

Set your Future AGI credentials in the application process. For self-hosted Future AGI using the [Helm port-forward setup](../../../src/pages/docs/self-hosting/helm.mdx), set `FI_BASE_URL` to the collector forwarded on port 4318. If you forward it elsewhere, use that collector origin instead. For Future AGI Cloud, leave `FI_BASE_URL` unset. Neither value points at Helicone.

```bash
export FI_API_KEY="your-futureagi-api-key"
export FI_SECRET_KEY="your-futureagi-secret-key"
export FI_BASE_URL="http://localhost:4318"  # self-hosted Future AGI only
export HELICONE_SURFACE="gateway"
export HELICONE_BASE_URL="http://localhost:8080/ai"
export HELICONE_API_KEY="local-placeholder"  # only for a local gateway with authentication disabled
export HELICONE_MODEL="openai/gpt-4o-mini"     # replace with a model configured on your gateway
```

If your gateway requires authentication, provide its actual key as `HELICONE_API_KEY` instead. The OpenAI-compatible client's `api_key` is sent to Helicone, not in Future AGI's tracing headers.

## Run a call

Choose Python 3.10–3.13 or Node.js 22.18+:

```bash
# Python, from this directory
python3 -m venv .venv
. .venv/bin/activate
pip install traceAI-openai==0.1.12 fi-instrumentation-otel==1.2.2 openai==3.42.1
python python/run_demo.py --project helicone-demo --scenario stream
```

```bash
# TypeScript, from this directory (Node.js 22.18+)
cd typescript
npm ci
DEMO_SCENARIOS=chat FI_PROJECT_NAME=helicone-demo-ts node run-demo.ts
```

Open **Observe** and select `helicone-demo` or `helicone-demo-ts`. Non-streamed calls use the response model and token usage when supplied by the upstream. Streamed calls in both SDKs retain the requested model, not the response model, in span model attributes; they do not establish which model the gateway ultimately served. Use non-streamed calls when you need the resolved model identity.

The Python stream above requests usage with `stream_options={"include_usage": True}` and records token counts when the upstream sends them. **TypeScript `@traceai/openai` 0.1.15 does not map streamed Chat Completions token usage to span attributes**, even with `stream_options: { include_usage: true }`. Use Python when you need streamed token metrics. A short-lived process flushes spans before exit.

To exclude prompt and response content from Future AGI spans, set `FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true` **before** starting either example. For Python, also set `FI_HIDE_LLM_INVOCATION_PARAMETERS=true` to hide invocation parameters. **TypeScript does not mask tool definitions or `gen_ai.request.parameters`** with these flags; use Python instead if tool schemas or invocation parameters are sensitive. Helicone still receives the requests because it handles the gateway calls.
