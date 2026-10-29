# Mirascope tracing with Future AGI (recipe)

Sends the OpenTelemetry spans that [Mirascope](https://github.com/Mirascope/mirascope) 2.5.0 already
emits (`ops.instrument_llm()`, `@ops.trace`, `ops.span`, `ops.session`) to Future AGI. There is no
traceAI package for Mirascope. The page is
[`src/pages/docs/integrations/frameworks/mirascope.mdx`](../../../src/pages/docs/integrations/frameworks/mirascope.mdx).

| File | What it is |
| --- | --- |
| `futureagi_tracing.py` | The recipe: `build_tracer_provider()` returns a tracer provider with the `project_name` resource, the OTLP/HTTP exporter (both auth headers, no gzip) and a filter that keeps content off the wire unless you opt in. Copy this file. |
| `app.py` | A small app that calls the recipe, then `ops.configure(...)` and `ops.instrument_llm()`. Scenarios: `chat`, `tool`, `agent`, `stream`, `error`, `trace`. |
| `run_e2e.sh` | Creates a venv, runs the tests, then runs every scenario against a model endpoint and a Future AGI collector. |
| `tests/` | 68 tests, no keys and no network beyond loopback. They run `app.py` as a subprocess against `tests/fake_openai.py` (a stand-in for a model) and `tests/recorder.py` (a stand-in collector that keeps the bytes it receives). |

## Run it

```bash
cd examples/frameworks/mirascope
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # no keys needed

export FI_API_KEY=... FI_SECRET_KEY=...
export FI_PROJECT_NAME=my-mirascope-test
export OPENAI_API_KEY=... MIRASCOPE_MODEL=openai/gpt-4o-mini
# self-hosted Future AGI: export FI_BASE_URL=http://localhost:4318
# any OpenAI-compatible endpoint:  export OPENAI_BASE_URL=https://.../v1
.venv/bin/python app.py chat
```

Or everything at once: `./run_e2e.sh` (tests, then every scenario twice: metadata only into
`$FI_PROJECT_NAME`, then `FI_CAPTURE_CONTENT=1` into `$FI_PROJECT_NAME-content`).

`pip install "mirascope[openai,ops]"` is not enough: Mirascope switches its `ops` module on only
when the Anthropic and Google GenAI OpenTelemetry instrumentors can be imported, and those import
their provider SDKs. `requirements.txt` has the working set.

## Privacy

Metadata only by default. Mirascope itself has no switch for content: `ops.instrument_llm()` always
writes the messages onto the span. `ContentFilterExporter` in `futureagi_tracing.py` is the off
switch; it drops every attribute that is not on the `METADATA_ATTRIBUTES` list, the payload of
events, and the text of errors. `FI_CAPTURE_CONTENT=1` (or `build_tracer_provider(capture_content=True)`)
turns content on. A stack trace is never exported in either mode.
