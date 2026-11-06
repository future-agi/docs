"""Scenarios for the tests and run_e2e.sh: the quickstart assistant with a few variations.

    python app.py chat | tool-error | model-error

Environment (all optional except the Future AGI and model keys):
    FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL, FI_PROJECT_NAME, FI_CAPTURE_CONTENT
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL      any OpenAI-compatible endpoint
    APP_PROMPT        the user message (default: What is the weather in Paris?)
    APP_USER_ID       set InvokeContext.user_id
    APP_CONVERSATION  set InvokeContext.conversation_id (default graphite-tracing-demo)
    APP_SYSTEM        the system prompt
    APP_KWARGS        a string stored in InvokeContext.kwargs["note"] (a dict-valued attribute)
    GRAFI_PROVIDER_SPANS=1   also enable the OpenInference OpenAI instrumentor (adds a second LLM span)
    APP_NO_SHUTDOWN=1        exit without calling provider.shutdown() (the atexit hook must flush)
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from grafi.common.decorators.llm_function import llm_function
from grafi.common.events.topic_events.publish_to_topic_event import PublishToTopicEvent
from grafi.common.models.invoke_context import InvokeContext
from grafi.common.models.message import Message
from grafi.runtime import ExecutionServices, GrafiRuntime
from grafi.tools.function_calls.function_call_tool import FunctionCallTool

from futureagi_grafi import create_tracer_provider
from quickstart import WeatherAssistant, WeatherTool

SCENARIOS = ("chat", "tool-error", "model-error")


class FailingWeatherTool(FunctionCallTool):
    """The same tool, but the weather backend is down."""

    name: str = "WeatherTool"

    @llm_function
    def get_weather(self, city: str) -> str:
        """Get the current weather for a city.

        Args:
            city (str): Name of the city.

        Returns:
            str: A short weather report.
        """
        raise RuntimeError(f"weather backend refused the request for {city}")


def build(scenario: str) -> WeatherAssistant:
    model = "model-that-does-not-exist" if scenario == "model-error" else os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")
    tool = FailingWeatherTool() if scenario == "tool-error" else WeatherTool()
    return (
        WeatherAssistant.builder()
        .api_key(os.environ.get("OPENAI_API_KEY"))
        .base_url(os.environ.get("OPENAI_BASE_URL"))
        .model(model)
        .system_prompt(
            os.environ.get("APP_SYSTEM", "Use the get_weather tool for weather questions. Answer in one short sentence.")
        )
        .function_call_tool(tool)
        .build()
    )


async def run(scenario: str) -> int:
    provider = create_tracer_provider()
    if os.environ.get("GRAFI_PROVIDER_SPANS") == "1":
        from openinference.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument(tracer_provider=provider)
    runtime = GrafiRuntime(ExecutionServices(tracer=provider.get_tracer("grafi")))
    context = InvokeContext(
        conversation_id=os.environ.get("APP_CONVERSATION", "graphite-tracing-demo"),
        invoke_id=uuid.uuid4().hex,
        assistant_request_id=uuid.uuid4().hex,
        user_id=os.environ.get("APP_USER_ID", ""),
        kwargs={"note": os.environ["APP_KWARGS"]} if os.environ.get("APP_KWARGS") else {},
    )
    request = PublishToTopicEvent(
        invoke_context=context,
        data=[Message(role="user", content=os.environ.get("APP_PROMPT", "What is the weather in Paris?"))],
    )
    code = 0
    try:
        events = [event async for event in runtime.invoke(build(scenario), request)]
        print(f"RESULT scenario={scenario} status=ok answer={events[0].data[0].content!r}")
    except Exception as error:  # noqa: BLE001 - the failure scenarios expect this
        print(f"RESULT scenario={scenario} status=error type={type(error).__name__}")
        code = 0 if scenario != "chat" else 1
    finally:
        if os.environ.get("APP_NO_SHUTDOWN") != "1":
            provider.shutdown()
    return code


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        sys.exit(f"usage: app.py {'|'.join(SCENARIOS)}")
    sys.exit(asyncio.run(run(sys.argv[1])))
