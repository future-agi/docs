# AgentScope 2.x with Future AGI tracing

Runnable companion to the docs page `docs/integrations/frameworks/agentscope`: trace an [AgentScope](https://github.com/agentscope-ai/agentscope) 2.x agent in Future AGI with AgentScope's own `TracingMiddleware` and an OpenTelemetry exporter you configure. There is no traceAI package for AgentScope.

AgentScope 2.x takes no endpoint, headers or resource. Its middleware records spans on the global OpenTelemetry tracer, so the application owns the tracer provider. `futureagi_tracing.py` builds that provider for Future AGI: `project_name` on the resource, `X-Api-Key` and `X-Secret-Key` on an OTLP/HTTP exporter, no gzip, and a content filter that keeps prompts, answers, tool payloads and error text out of the export unless you opt in.

## Layout

| Path | What it is |
| --- | --- |
| `futureagi_tracing.py` | `setup_tracing()`: the provider, the exporter, and `ContentFilterExporter` (metadata only by default, `FI_CAPTURE_CONTENT=1` to opt in). The page shows this file. |
| `quickstart.py` | The smallest traced agent: one tool, one reply, flush. The page shows this file. |
| `app.py` | The same agent with four scenarios: `chat`, `nostream`, `tool-error`, `model-error`. Used by the tests and `run_e2e.sh`. |
| `legacy_1x/app_1x.py` | The AgentScope 1.x leg (`agentscope.init(tracing_url=...)` plus OpenTelemetry environment variables). Needs a separate environment, see below. |
| `tests/` | 21 tests on 2.x (3 more on 1.x, which skip on 2.x): contract (hierarchy, model, tokens, headers, path, no gzip), privacy marker scans of every byte the collector receives, attribute drift guard, flush, dead collector, two projects, page sync, and the 1.x leg. No Future AGI stack needed. |
| `tests/fake_openai.py` | A small OpenAI-compatible server for the tests (tool call, answer, streaming, usage, an error model). Not OpenAI. |
| `run_e2e.sh` | Tests, then the agent against a real model and a real Future AGI collector. |

## Install

Python 3.11, 3.12 or 3.13.

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt     # pins agentscope 2.0.10
```

## Run

Tests only (no network, no keys):

```bash
python -m pytest
```

End to end against a Future AGI collector (self-hosted shown) and a model:

```bash
FI_API_KEY=... FI_SECRET_KEY=... FI_BASE_URL=http://localhost:4318 \
OPENAI_API_KEY=... OPENAI_BASE_URL=... OPENAI_MODEL=... ./run_e2e.sh
```

`run_e2e.sh` creates `.venv` if there is none, runs the tests, runs `app.py` four times into project `agentscope-e2e` (or `FI_PROJECT_NAME`), then once more with `FI_CAPTURE_CONTENT=1` into `<project>-content`. Without `OPENAI_API_KEY` it starts the local stand-in from `tests/fake_openai.py`, which is not a real model, so the script runs anywhere.

Other AgentScope versions: `VENV_DIR=/path/to/venv ./run_e2e.sh` with a venv that has the version you want (`pip install agentscope==2.0.9`).

## Configure

| Variable | Required | Purpose |
| --- | --- | --- |
| `FI_API_KEY`, `FI_SECRET_KEY` | Yes | Future AGI key pair. Sent as `X-Api-Key` and `X-Secret-Key` to the collector only. |
| `FI_PROJECT_NAME` | No | Observe project. Default `agentscope-app`. |
| `FI_BASE_URL` | No | Collector origin. Traces go to `$FI_BASE_URL/tracer/v1/traces`. Default `https://api.futureagi.com`. |
| `FI_CAPTURE_CONTENT` | No | `1` exports prompts, answers, tool arguments and results, and error text. Default off. |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | For the model | Any OpenAI-compatible endpoint, used by `app.py` and `quickstart.py`. |

## Privacy

AgentScope 2.x has no switch for content: `TracingMiddleware` always writes `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.tool.definitions`, `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` onto its spans. `ContentFilterExporter` removes them before export unless `FI_CAPTURE_CONTENT=1`. It keeps an allow-list of metadata attributes (`METADATA_ATTRIBUTES`), so an attribute a later AgentScope release adds stays private until reviewed, and `tests/test_privacy.py::test_every_attribute_is_classified` fails when that happens. A stack trace is never exported, in either mode.

A unique marker placed in the system prompt, the user prompt, the tool arguments, the tool result, the answer and an error message was absent from every byte the collector received (`tests/test_privacy.py`), and absent from all 47 ClickHouse tables and a full Postgres dump of a local Future AGI stack. With `FI_CAPTURE_CONTENT=1` it is present in the span attributes. See the docs page for the table.

## AgentScope 1.x leg

1.x has no middleware and builds its own exporter in `agentscope.init(tracing_url=...)`. It takes no headers or resource, so the standard OpenTelemetry environment variables carry the keys and the project name (see the docstring in `legacy_1x/app_1x.py`). A clean install of 1.0.21 needs a few pins today:

```bash
python3.13 -m venv .venv-1x && . .venv-1x/bin/activate
pip install "agentscope==1.0.21" "mcp<2" "openai<3" greenlet tqdm pytest protobuf opentelemetry-proto
python -m pytest tests/test_legacy_1x.py     # the 2.x tests skip themselves on 1.x
```

1.x has no content switch: prompts, answers and tool payloads are always exported.

## What was and was not verified

Run on 2026-10-15 and 2026-10-16 with `agentscope` 2.0.10 (and 2.0.9, and 1.0.21 for the 1.x leg), `opentelemetry-sdk` 1.45.1, `openai` 3.31.0, Python 3.13.15 and 3.11.12, against a self-hosted Future AGI stack.

| Verified | How |
| --- | --- |
| Spans land in the project named on the resource, one trace per reply, reply span with model and tool children, model id, provider and tokens | `run_e2e.sh` against a local OpenAI-compatible proxy running a real model; `fi_verify` on the stored spans |
| Streaming and non-streaming model calls, both | `chat` and `nostream` scenarios |
| A failed model call is `ERROR` on the `chat` and `invoke_agent` spans and the trace is still exported | `model-error` scenario, tests and end to end |
| A raising tool does not make its span `ERROR` (AgentScope turns it into an error result) | `tool-error` scenario, `test_tool_exception_does_not_fail_the_tool_span` |
| Content off by default, on with `FI_CAPTURE_CONTENT=1`; no username, host name, path, stack trace or key stored | marker scans, see Privacy |
| Keys never cross: the model key reaches the model only, the Future AGI keys reach the collector only | `tests/test_recipe.py` |
| A dead collector does not fail the agent; a normal exit flushes; a provider installed after the agent is built still traces; no provider means no spans and no error | `tests/test_recipe.py` |
| gzip stays off even with `OTEL_EXPORTER_OTLP_COMPRESSION=gzip` set | `tests/test_recipe.py` |
| Two projects stay apart | `tests/test_recipe.py`, and twelve local projects (28 traces, 102 spans) in which no trace id appeared in two projects |
| 2.0.9 and 2.0.10 behave the same | the same tests and end-to-end run on both; the `_tracing` module differs only by one added provider name |
| 1.0.21 works through `tracing_url` plus environment variables | `tests/test_legacy_1x.py` and an end-to-end run |

| **Not** verified | Why |
| --- | --- |
| The hosted `api.futureagi.com` collector | Only a self-hosted stack was used |
| Model classes other than `OpenAIChatModel` | Five Gemini attempts (`gemini-3.8-flash`, `gemini-3.7-flash`) were all answered `503 UNAVAILABLE` by the Gemini API, so no Gemini run completed |
| Human-in-the-loop and external-execution replies, multi-agent pipelines, `create_app` service agents, MCP tools | Not run |
| Future AGI typing the reply span as an agent, filling Input and Output, mapping `gen_ai.conversation.id` to a session | Not done by this recipe: that is normalization in Future AGI's shared span processor |
