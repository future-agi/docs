"""An AgentScope 2.x agent traced to Future AGI.

    python app.py [chat|nostream|tool-error|model-error] [--prompt TEXT] [--system TEXT]

chat         one reply with a tool round trip, streaming model calls (AgentScope's default)
nostream     the same with ``stream=False``
tool-error   the tool raises
model-error  the model call fails (a model name the endpoint does not serve)

Environment: FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL (self-hosted only), FI_PROJECT_NAME,
FI_CAPTURE_CONTENT (see futureagi_tracing.py), and for the model OPENAI_API_KEY,
OPENAI_BASE_URL, OPENAI_MODEL. Any OpenAI-compatible endpoint works.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg
from agentscope.middleware import TracingMiddleware
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

from futureagi_tracing import setup_tracing

ALLOW = PermissionDecision(behavior=PermissionBehavior.ALLOW, message="example tool")


def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city (`str`): The city name.
    """
    return f"It is 21 C and sunny in {city}."


def lookup_order(order_id: str) -> str:
    """Look up an order by its id.

    Args:
        order_id (`str`): The order id.
    """
    raise ValueError(f"order service refused order {order_id}")


def build_agent(scenario: str, system: str) -> Agent:
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4.1")
    if scenario == "model-error":
        model_name = "model-that-does-not-exist"
    tool = lookup_order if scenario == "tool-error" else get_weather
    return Agent(
        name="support-agent",
        system_prompt=system,
        model=OpenAIChatModel(
            credential=OpenAICredential(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url=os.environ.get("OPENAI_BASE_URL"),
            ),
            model=model_name,
            stream=scenario != "nostream",
            max_retries=0,
        ),
        toolkit=Toolkit(tools=[FunctionTool(tool, permission=ALLOW)]),
        # The middleware emits the spans. It needs a tracer provider to exist (setup_tracing).
        middlewares=[TracingMiddleware()],
        state=AgentState(session_id="support-chat-42"),
    )


async def run(scenario: str, prompt: str, system: str) -> str:
    reply = await build_agent(scenario, system).reply(UserMsg(name="user", content=prompt))
    return reply.get_text_content()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", nargs="?", default="chat", choices=["chat", "nostream", "tool-error", "model-error"])
    parser.add_argument("--prompt", help="default: a weather question, or an order question for tool-error")
    parser.add_argument("--system", default="You are a helpful assistant. Use the tool you are given.")
    args = parser.parse_args()
    if args.prompt is None:
        args.prompt = (
            "Look up order A-1001 and tell me its status."
            if args.scenario == "tool-error"
            else "What is the weather in Paris?"
        )

    # 1. Own the tracer provider, once, before the first reply. AgentScope will not do it.
    provider = setup_tracing()

    code = 0
    try:
        print("RESULT", args.scenario, "ok", repr(asyncio.run(run(args.scenario, args.prompt, args.system))))
    except Exception as exc:  # the example reports failures; the spans carry them too
        print("RESULT", args.scenario, "error", type(exc).__name__)
        code = 1
    # 2. Short scripts: send what is buffered before the process exits.
    provider.force_flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
