"""The smallest traced Graphite run: one tool, one question, then flush.

    FI_API_KEY=... FI_SECRET_KEY=... OPENAI_API_KEY=... python quickstart.py

Graphite's tracer comes from ``ExecutionServices`` and the assistant must be run through
``GrafiRuntime.invoke``. Do not call ``grafi.common.instrumentations.tracing.setup_tracing``.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Self

from grafi.assistants.assistant import Assistant
from grafi.assistants.assistant_base import AssistantBaseBuilder
from grafi.common.decorators.llm_function import llm_function
from grafi.common.events.topic_events.publish_to_topic_event import PublishToTopicEvent
from grafi.common.models.invoke_context import InvokeContext
from grafi.common.models.message import Message
from grafi.nodes.node import Node
from grafi.runtime import ExecutionServices, GrafiRuntime
from grafi.tools.function_calls.function_call_tool import FunctionCallTool
from grafi.tools.llms.impl.openai_tool import OpenAITool
from grafi.topics.conditions import has_text_response, has_tool_call
from grafi.topics.expressions.subscription_builder import SubscriptionBuilder
from grafi.topics.topic_impl.input_topic import InputTopic
from grafi.topics.topic_impl.output_topic import OutputTopic
from grafi.topics.topic_impl.topic import Topic
from grafi.workflows.impl.event_driven_workflow import EventDrivenWorkflow
from loguru import logger

from futureagi_grafi import create_tracer_provider

logger.remove()  # Graphite logs every queue poll at DEBUG through loguru
logger.add(sys.stderr, level="WARNING")


# --- your application: a Graphite assistant with one function tool ------------------------
class WeatherTool(FunctionCallTool):
    name: str = "WeatherTool"

    @llm_function
    def get_weather(self, city: str) -> str:
        """Get the current weather for a city.

        Args:
            city (str): Name of the city.

        Returns:
            str: A short weather report.
        """
        return f"The weather in {city} is sunny, 21C."


class WeatherAssistant(Assistant):
    name: str = "WeatherAssistant"
    type: str = "WeatherAssistant"
    api_key: str | None = None
    base_url: str | None = None
    model: str = "gpt-4.1-nano"
    system_prompt: str | None = None
    function_call_tool: FunctionCallTool

    @classmethod
    def builder(cls) -> WeatherAssistantBuilder:
        return WeatherAssistantBuilder(cls)

    def _construct_workflow(self) -> Self:
        input_topic = InputTopic(name="agent_input_topic")
        output_topic = OutputTopic(name="agent_output_topic", condition=has_text_response)
        call_topic = Topic(name="function_call_topic", condition=has_tool_call)
        result_topic = Topic(name="function_result_topic")

        llm = OpenAITool.builder().name("ChatLLM").api_key(self.api_key).model(self.model)
        if self.base_url:
            llm = llm.base_url(self.base_url)
        llm_node = (
            Node.builder()
            .name("LLMNode")
            .type("LLMNode")
            .subscribe(
                SubscriptionBuilder()
                .subscribed_to(input_topic)
                .or_()
                .subscribed_to(result_topic)
                .build()
            )
            .tool(llm.system_message(self.system_prompt).build())
            .publish_to(call_topic)
            .publish_to(output_topic)
            .build()
        )
        tool_node = Node(
            name="ToolNode",
            type="ToolNode",
            tool=self.function_call_tool,
            subscribed_expressions=[SubscriptionBuilder().subscribed_to(call_topic).build()],
            publish_to=[result_topic],
        )
        self.workflow = (
            EventDrivenWorkflow.builder()
            .name("tool_workflow")
            .node(llm_node)
            .node(tool_node)
            .build()
        )
        return self


class WeatherAssistantBuilder(AssistantBaseBuilder[WeatherAssistant]):
    def api_key(self, value: str | None) -> Self:
        self.kwargs["api_key"] = value
        return self

    def base_url(self, value: str | None) -> Self:
        self.kwargs["base_url"] = value
        return self

    def model(self, value: str) -> Self:
        self.kwargs["model"] = value
        return self

    def system_prompt(self, value: str) -> Self:
        self.kwargs["system_prompt"] = value
        return self

    def function_call_tool(self, value: FunctionCallTool) -> Self:
        self.kwargs["function_call_tool"] = value
        return self


def build_assistant(tool: FunctionCallTool | None = None) -> WeatherAssistant:
    return (
        WeatherAssistant.builder()
        .api_key(os.environ.get("OPENAI_API_KEY"))
        .base_url(os.environ.get("OPENAI_BASE_URL"))
        .model(os.environ.get("OPENAI_MODEL", "gpt-4.1-nano"))
        .system_prompt("Use the get_weather tool for weather questions. Answer in one short sentence.")
        .function_call_tool(tool or WeatherTool())
        .build()
    )


# --- tracing: the part this page is about --------------------------------------------------
async def main() -> None:
    provider = create_tracer_provider()  # reads FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME, FI_BASE_URL
    runtime = GrafiRuntime(ExecutionServices(tracer=provider.get_tracer("grafi")))
    context = InvokeContext(
        conversation_id="graphite-tracing-demo",  # becomes the Future AGI session
        invoke_id=uuid.uuid4().hex,
        assistant_request_id=uuid.uuid4().hex,
    )
    request = PublishToTopicEvent(
        invoke_context=context,
        data=[Message(role="user", content="What is the weather in Paris?")],
    )
    try:
        events = [event async for event in runtime.invoke(build_assistant(), request)]
        print(events[0].data[0].content)
    finally:
        provider.shutdown()  # flush the last batch before the process exits


if __name__ == "__main__":
    asyncio.run(main())
