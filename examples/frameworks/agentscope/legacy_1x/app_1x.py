"""AgentScope 1.x (tested: 1.0.21, the last 1.x release) traced to Future AGI.

1.x builds its own exporter inside ``agentscope.init(tracing_url=...)``: an OTLP/HTTP
exporter with no headers argument and a tracer provider with no resource argument. The
standard OpenTelemetry environment variables are the only way to give them the Future AGI
keys and the project name, so set these before the process starts:

    export OTEL_EXPORTER_OTLP_TRACES_HEADERS="X-Api-Key=$FI_API_KEY,X-Secret-Key=$FI_SECRET_KEY"
    export OTEL_RESOURCE_ATTRIBUTES="project_name=my-agent,project_type=observe"

1.x has no switch for content: prompts, answers and tool payloads are always on the spans.
This is the 1.x leg of the conformance matrix. New work should use AgentScope 2.x and app.py.

    python legacy_1x/app_1x.py        # needs OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, FI_BASE_URL
"""

from __future__ import annotations

import asyncio
import os
import sys

import agentscope
from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg, TextBlock
from agentscope.model import OpenAIChatModel
from agentscope.tool import ToolResponse, Toolkit

# Point 1.x tracing at Future AGI. The path is /tracer/v1/traces; HTTP, not gRPC.
agentscope.init(
    project="agentscope-1x",
    tracing_url=os.environ.get("FI_BASE_URL", "https://api.futureagi.com").rstrip("/") + "/tracer/v1/traces",
)


def get_weather(city: str) -> ToolResponse:
    """Get the current weather for a city.

    Args:
        city (`str`): The city name.
    """
    return ToolResponse(content=[TextBlock(type="text", text=f"It is 21 C and sunny in {city}.")])


async def main() -> int:
    toolkit = Toolkit()
    toolkit.register_tool_function(get_weather)
    agent = ReActAgent(
        name="support-agent",
        sys_prompt=os.environ.get("SYSTEM", "You are a helpful assistant. Use the tool you are given."),
        model=OpenAIChatModel(
            model_name=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
            api_key=os.environ["OPENAI_API_KEY"],
            stream=True,
            client_kwargs={"base_url": os.environ["OPENAI_BASE_URL"]} if os.environ.get("OPENAI_BASE_URL") else None,
        ),
        formatter=OpenAIChatFormatter(),
        toolkit=toolkit,
        memory=InMemoryMemory(),
    )
    agent.set_console_output_enabled(False)
    reply = await agent(Msg("user", os.environ.get("PROMPT", "What is the weather in Paris?"), "user"))
    print("RESULT chat ok", repr(reply.get_text_content()))
    return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    # 1.x batches spans; flush before a short script exits.
    from opentelemetry import trace

    trace.get_tracer_provider().force_flush()
    sys.exit(code)
