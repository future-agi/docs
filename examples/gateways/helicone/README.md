# Trace Helicone gateway calls with Future AGI

Runnable companion to the docs page [Trace Helicone gateway calls in Observe](../../../src/pages/docs/integrations/gateways/helicone.mdx). It traces OpenAI-client calls that go through Helicone with the existing `traceAI-openai` (Python) and `@traceai/openai` (TypeScript) instrumentors. There is no Helicone package and no receiver.

**Status: alpha.** No Helicone account was used and `ai-gateway.helicone.ai` / `oai.helicone.ai` are never called. `STANDIN` marks every place a local stand-in replaces a Helicone endpoint.

## What is here

| Path | What it is |
| --- | --- |
| `python/helicone_tracing.py` | The recipe: `register()`, instrument, and a client for each Helicone surface (AI Gateway, classic proxy) |
| `python/redact_errors.py` | Exporter wrapper that drops error text and stack traces before export |
| `python/run_demo.py` | Agent with a tool call, a streamed call and a failing call, under an agent span |
| `typescript/` | The TypeScript recipe and the same demo (`npm install`, then `node run-demo.ts`; Node 22.18+) |
| `support/mock_helicone.py` | `STANDIN`: an OpenAI-compatible server that enforces each Helicone surface's auth shape |
| `support/otlp_capture.py` | A local OTLP/HTTP receiver that decodes what `register()` exports |
| `tests/` | Conformance tests (below) |
| `run_e2e.sh` | The real self-hosted Helicone AI Gateway in front of an upstream you choose, traced into Future AGI |

## Run the tests

No network, no keys. The tests start the stand-in and the OTLP receiver on loopback.

```bash
python3.13 -m venv .venv && . .venv/bin/activate     # traceAI-openai supports Python 3.10 to 3.13
pip install -r requirements.txt
(cd typescript && npm install)                        # optional; the TypeScript tests skip without it
python -m pytest tests -q
```

What the tests assert, with the acceptance criterion from the PRD each one covers:

- **AC-01** Two surfaces, two auths: the gateway client sends the Helicone key as `Authorization` and no `Helicone-Auth`; the proxy client sends the provider key plus `Helicone-Auth`; each surface's client fails with 401 on the other's URL.
- **AC-02** Model, usage, `project_name` and `project_type` on the exported span; agent, tool and LLM spans nest correctly; the OTLP request has the Future AGI key headers and is not compressed.
- **AC-03** `FI_HIDE_INPUTS` / `FI_HIDE_OUTPUTS` keep a unique marker and an email out of every field of every exported span (prompts, answers, tool arguments and tool results); without them they are exported. The tool-definition and error-text gaps are pinned in their own tests.
- **AC-05** `Helicone-Session-Id`, `Helicone-User-Id`, `Helicone-Property-*` reach Helicone and are not on any span; `using_session` / `using_user` are how a Future AGI session and user are set.
- **AC-06** No Helicone or provider key reaches the collector; no real key is in this directory.
- The base URLs the page publishes, built by the OpenAI SDK on an in-process transport (`STANDIN`), give the paths and headers the page describes.
- TypeScript known gaps are pinned by tests that fail when the gap is fixed: failed calls leave no span, streamed calls have no tokens, the hide settings do not apply.

The Python assertions hold for traceAI-openai 0.1.10 and for the unreleased change in future-agi/traceAI#249, and for openai 1.69.0 and 3.31.0.

## Run it end to end

`run_e2e.sh` installs the Helicone AI Gateway (`@helicone/ai-gateway`, default 0.2.0-beta.30), starts it on `127.0.0.1` in front of an OpenAI-compatible upstream you name, and runs the demos through it into Future AGI. The gateway is the real one; only its upstream is yours to choose. Nothing on `*.helicone.ai` is contacted. The script downloads the gateway from npm at run time and does not vendor it; the gateway repository's `LICENSE` is GPL-3.0 (its README says Apache), so check the terms before you redistribute it.

```bash
export E2E_UPSTREAM_URL=http://127.0.0.1:8317    # origin of any OpenAI-compatible server, no /v1
export E2E_UPSTREAM_KEY=...                       # its key (the gateway sends it; it is never printed)
export E2E_UPSTREAM_MODEL=...                     # a model it serves
export FI_API_KEY=... FI_SECRET_KEY=...           # Future AGI keys
export FI_BASE_URL=http://localhost:8080          # self-hosted Future AGI only
export FI_PROJECT_NAME=helicone-e2e
export FI_GRPC_ENDPOINT=http://localhost:14337    # optional: step 7, the gateway's own telemetry
./run_e2e.sh
```

It creates these Observe projects: `helicone-e2e` (default capture), `helicone-e2e-private` (content hidden and error details scrubbed), `helicone-e2e-ts` (TypeScript), `helicone-e2e-proxy-standin` (`STANDIN`: the classic-proxy shape) and, with `FI_GRPC_ENDPOINT`, `helicone-e2e-gateway-otlp`. It prints a unique marker; search your Future AGI storage for it to repeat the privacy check (it must be absent from `-private`).

## Single runs

```bash
export HELICONE_SURFACE=gateway                   # or proxy
export HELICONE_BASE_URL=https://ai-gateway.helicone.ai    # https://oai.helicone.ai/v1 for the classic proxy
export HELICONE_API_KEY=...                       # your Helicone key
export OPENAI_API_KEY=...                         # classic proxy only
export HELICONE_MODEL=gpt-4o-mini                 # an id from helicone.ai/models
python python/run_demo.py --project helicone-demo --scenario core
# content off, error details scrubbed:
FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_LLM_INVOCATION_PARAMETERS=true \
  python python/run_demo.py --project helicone-demo-private --scrub-errors --scenario core
```

Running against the hosted Helicone endpoints needs your own Helicone key and credits, and is not covered by the tests here.
