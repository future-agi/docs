# Open Agent Spec (pyagentspec) tracing example

Runnable companion to the docs page
[Open Agent Spec tracing with Future AGI](../../../src/pages/docs/integrations/frameworks/open-agent-spec.mdx).

An Oracle Open Agent Spec agent (one `OpenAiCompatibleConfig`, one `ServerTool`) is
compiled by pyagentspec's LangGraph adapter and traced into Future AGI with traceAI's
LangChain instrumentor. pyagentspec itself has no OpenTelemetry exporter.

| File | What it is |
| --- | --- |
| `futureagi_tracing.py` | The recipe: `setup_tracing()` = `register()` + an error-detail filter on the exporter + `LangChainInstrumentor`. Shown in full on the page. |
| `weather_agent.py` | The Agent Spec definition and the Python implementation of its tool. |
| `app.py` | Runs the agent: `chat`, `async`, `tool-error`, `model-error`. |
| `run_e2e.sh` | Tests, then every scenario against a real model and a Future AGI collector, content captured and content hidden. |
| `scripts/openinference_variant.py` | Comparison only: the same agent with Arize's `openinference-instrumentation-agentspec` (not a dependency of this recipe). |
| `scripts/record_fixture.py`, `scripts/replay_fixture.py` | Record one run as OTLP/JSON; post a recorded fixture to a Future AGI project. |
| `fixtures/` | Two recorded runs (real model, content hidden or masked): this recipe, and Arize's instrumentor. |
| `tests/` | Hermetic tests: a model stand-in (`fake_openai.py`, not a model) and a loopback OTLP recorder. No keys, no network beyond 127.0.0.1. |

Tested 2026-10-16: `pyagentspec` 26.3.1 (`langgraph` 1.2.15, `langchain-core` 1.6.11,
`langchain-openai` 1.2.2), `traceai-langchain` 0.2.0, `fi-instrumentation-otel` 1.1.0,
`opentelemetry-sdk` 1.45.1, Python 3.13.15 and 3.10.17. LangGraph adapter only.

## Run the tests

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

On Python 3.10 one test is an expected failure (`xfail`): an `ainvoke` run splits into one
trace per model call there, because LangChain cannot carry the run context into asyncio
tasks before Python 3.11. Plain LangGraph does the same.

## Run end to end

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
MODEL_BASE_URL=https://your-openai-compatible-endpoint/v1 MODEL_API_KEY=... MODEL_ID=... \
./run_e2e.sh
```

Traces land in `$FI_PROJECT_NAME` (traceAI default: content captured) and
`$FI_PROJECT_NAME-hidden` (`FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true`). Each question carries
a fresh marker, listed in `.e2e/markers.txt`, so you can search the stored traces for it.
`RUN_OPENINFERENCE=1` adds the Arize comparison runs (install
`openinference-instrumentation-agentspec==0.1.15` first). Without `MODEL_BASE_URL` the script
uses the stand-in in `tests/fake_openai.py` and says so: that is a smoke run, not a model.

## Fixtures

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=... FI_PROJECT_NAME=agent-spec-fixture \
python scripts/replay_fixture.py fixtures/agentspec-26.3.1-langgraph-traceai.otlp.json
```

The replay gives the recorded spans fresh ids and timestamps and keeps everything else. The
fixtures hold no prompts, answers or tool payloads; the model endpoint URL was replaced by
`http://localhost:8000/v1`.
