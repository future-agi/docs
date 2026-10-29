"""A small Mirascope app traced into Future AGI.

    python app.py chat | tool | agent | stream | error | trace

* chat    one non-streaming ``Model.call``
* tool    a call that asks for a tool, runs it, and resumes the conversation (Mirascope's own
          loop, with nothing around it)
* agent   the same loop inside an ``@ops.trace`` function, so it lands in one trace
* stream  one ``Model.stream`` consumed to the end
* error   a call the provider rejects (unknown model): the span ends in ERROR
* trace   ``@ops.trace``, ``ops.span`` and ``ops.session`` around two calls

Environment
    FI_API_KEY, FI_SECRET_KEY            Future AGI keys
    FI_BASE_URL                          default https://api.futureagi.com
    FI_PROJECT_NAME                      the Observe project (default mirascope-app)
    FI_CAPTURE_CONTENT=1                 also export prompts, answers and arguments
    OPENAI_API_KEY, OPENAI_BASE_URL      any OpenAI-compatible endpoint
    MIRASCOPE_MODEL                      default openai/gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import sys

from mirascope import llm, ops

from futureagi_tracing import build_tracer_provider

MODEL_ID = os.environ.get("MIRASCOPE_MODEL", "openai/gpt-4o-mini")
# A marker the privacy checks look for. It is in the prompt, the tool argument and the tool
# result, so a leak through any of them is caught.
CITY = os.environ.get("DEMO_CITY", "Lisbon")

WEATHER = {"Lisbon": "sunny, 24 C", "Oslo": "rain, 7 C"}


@llm.tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    # Mirascope does not emit a span for a tool run. This span is the app's own, and the
    # two GenAI attributes make Future AGI show it as a tool.
    with ops.span(
        "execute_tool get_weather",
        **{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "get_weather", "city": city},
    ) as span:
        result = WEATHER.get(city, f"no data for {city}")
        span.set(result=result)
        return result


def scenario_chat(model: llm.Model) -> str:
    return model.call(f"Reply with one short sentence about {CITY}.").text()


def scenario_tool(model: llm.Model) -> str:
    response = model.call(
        f"What is the weather in {CITY}? Use the get_weather tool, then answer in one sentence.",
        tools=[get_weather],
    )
    while response.tool_calls:
        response = response.resume(response.execute_tools())
    return response.text()


@ops.trace
def weather_agent(question: str, model: llm.Model) -> str:
    response = model.call(question, tools=[get_weather])
    while response.tool_calls:
        response = response.resume(response.execute_tools())
    return response.text()


def scenario_agent(model: llm.Model) -> str:
    return weather_agent(
        f"What is the weather in {CITY}? Use the get_weather tool, then answer in one sentence.",
        model,
    )


def scenario_stream(model: llm.Model) -> str:
    response = model.stream(f"Name two landmarks in {CITY}, in one line.")
    return "".join(response.text_stream())


def scenario_error(_model: llm.Model) -> str:
    # The provider rejects this model id, so the call raises and its span ends in ERROR.
    provider, _, rest = MODEL_ID.partition("/")
    suffix = ":" + rest.split(":", 1)[1] if ":" in rest else ""  # keep :completions / :responses
    llm.Model(f"{provider}/no-such-model-for-the-demo{suffix}").call(f"Say hello to {CITY}.")
    return "unreachable"


@ops.trace
def summarize(topic: str, model: llm.Model) -> str:
    return model.call(f"One sentence about {topic}.").text()


def scenario_trace(model: llm.Model) -> str:
    with ops.session(id="mirascope-demo-session", attributes={"channel": "cli"}):
        with ops.span("plan", topic=CITY) as span:
            span.info(f"planning about {CITY}")
            return summarize(CITY, model)


SCENARIOS = {
    "chat": scenario_chat,
    "tool": scenario_tool,
    "agent": scenario_agent,
    "stream": scenario_stream,
    "error": scenario_error,
    "trace": scenario_trace,
}


def main(argv: list[str]) -> int:
    name = argv[1] if len(argv) > 1 else "chat"
    if name not in SCENARIOS:
        print(f"unknown scenario {name!r}; choose one of {', '.join(SCENARIOS)}", file=sys.stderr)
        return 2

    provider = build_tracer_provider()
    ops.configure(tracer_provider=provider)
    ops.instrument_llm()

    outcome: dict[str, object] = {"scenario": name, "model": MODEL_ID}
    try:
        outcome["answer"] = SCENARIOS[name](llm.Model(MODEL_ID))
        outcome["ok"] = True
    except Exception as exc:  # the error scenario lands here on purpose
        outcome["ok"] = False
        outcome["error"] = type(exc).__name__
    finally:
        provider.shutdown()  # flush now; the SDK also flushes at a normal interpreter exit
    print("RESULT", json.dumps(outcome))
    return 0 if outcome["ok"] or name == "error" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
