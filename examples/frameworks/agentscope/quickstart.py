import asyncio
import os

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg
from agentscope.middleware import TracingMiddleware
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

from futureagi_tracing import setup_tracing

# 1. Install the tracer provider once, before the first reply.
provider = setup_tracing(project_name="my-chatbot")


def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city (`str`): The city name.
    """
    return f"It is 21 C and sunny in {city}."


agent = Agent(
    name="weather-agent",
    system_prompt="You are a weather assistant. Always call get_weather before answering.",
    model=OpenAIChatModel(
        credential=OpenAICredential(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL"),  # any OpenAI-compatible endpoint
        ),
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
    ),
    toolkit=Toolkit(
        tools=[
            FunctionTool(
                get_weather,
                permission=PermissionDecision(behavior=PermissionBehavior.ALLOW, message="allowed"),
            )
        ]
    ),
    # 2. Add the middleware. It creates the spans.
    middlewares=[TracingMiddleware()],
    state=AgentState(session_id="support-chat-42"),
)

reply = asyncio.run(agent.reply(UserMsg(name="user", content="What is the weather in Paris?")))
print(reply.get_text_content())

# 3. Short scripts: send what is buffered before the process exits.
provider.force_flush()
