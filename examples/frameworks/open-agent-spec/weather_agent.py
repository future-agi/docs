"""The Agent Spec definition used by the example: one agent, one LLM config, one tool."""

from __future__ import annotations

import os

from pyagentspec.adapters.langgraph import AgentSpecLoader
from pyagentspec.agent import Agent
from pyagentspec.llms import OpenAiCompatibleConfig
from pyagentspec.property import StringProperty
from pyagentspec.tools import ServerTool


def get_weather(city: str) -> str:
    """The Python implementation behind the Agent Spec ServerTool ``get_weather``."""
    if os.environ.get("WEATHER_TOOL_FAILS") == "1":
        raise RuntimeError(f"weather service unavailable for {city}")
    return f"Sunny, 21 C in {city}."


def build_agent(api_key: str) -> Agent:
    llm = OpenAiCompatibleConfig(
        name="chat-model",
        url=os.environ["MODEL_BASE_URL"],
        model_id=os.environ["MODEL_ID"],
        api_key=api_key,
    )
    weather = ServerTool(
        name="get_weather",
        description="Get the current weather for a city.",
        inputs=[StringProperty(title="city")],
        outputs=[StringProperty(title="forecast")],
    )
    return Agent(
        name="weather_assistant",
        llm_config=llm,
        tools=[weather],
        system_prompt="You are a weather assistant. Call get_weather before you answer.",
    )


def load(api_key: str):
    """Compile the Agent Spec agent into a LangGraph graph with the LangGraph adapter."""
    return AgentSpecLoader(tool_registry={"get_weather": get_weather}).load_component(
        build_agent(api_key)
    )
