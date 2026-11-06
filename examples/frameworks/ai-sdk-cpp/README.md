# AI SDK C++: evidence for the "not supported" page

This folder backs [`src/pages/docs/integrations/frameworks/ai-sdk-cpp.mdx`](../../../src/pages/docs/integrations/frameworks/ai-sdk-cpp.mdx).
It is **not an integration**. AI SDK C++ (ClickHouse/ai-sdk-cpp) has no OTLP or OpenTelemetry export, so there is nothing to
set up and nothing here sends data to Future AGI.

| File | What it does |
| --- | --- |
| `check_pin.sh` | Shallow-clones the pinned commit and searches every tracked file for `otlp`, `opentelemetry`, `exporter`, `traceparent`, `gen_ai` and `/v1/traces`. Two positive controls (`langfuse`, `x-api-key`) must match, otherwise the result is not trusted. Exit 0 = page still true, 1 = an OTLP term appeared (reopen TH-8251), 2 = search not trusted. |
| `wire_probe/` | Builds the pinned SDK, runs its `ai::langfuse` module against a **loopback** capture stub, and checks what it puts on the wire and how `Trace::end()` behaves. Refuses any non-loopback Langfuse host. |
| `tests/` | Unit tests for the scripts and the page (no network, no compiler). Fixtures are a recorded probe run with fake keys. |

## Re-run the source check

```bash
./check_pin.sh                                   # the pinned commit
CHECK_PIN_SHA=<newer sha> ./check_pin.sh         # any other commit of ClickHouse/ai-sdk-cpp
```

## Re-run the wire probe

Needs git, cmake 3.16+, a C++20 compiler, OpenSSL, python3, GitHub access (the build downloads zlib) and an
OpenAI-compatible endpoint for the model call (the probe makes one tool call).

```bash
export PROBE_API_KEY=...                         # key for the endpoint, never committed
export PROBE_OPENAI_BASE=http://127.0.0.1:8317   # base URL without /v1
export PROBE_MODEL=gpt-6-luna
export OPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3   # macOS/Homebrew; cmake finds it elsewhere
./wire_probe/run_wire_probe.sh                   # about two minutes the first time
```

It runs five modes (`run`, `fail`, `noend`, `strict-down`, `best-down`) and prints one PASS or FAIL line per fact that the
page states. A FAIL means upstream behaviour changed and the page needs a new look.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```

(`pytest tests` also works.)
