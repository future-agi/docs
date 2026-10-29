"""A LangGraph weather agent traced with the watsonx Orchestrate Agentic SDK observability module.

The SDK (`ibm-watsonx-orchestrate-sdk`) exports OTLP/HTTP to the URL in WXO_OTLP_ENDPOINT. Point it
at the OpenTelemetry Collector in otelcol.yaml. The collector names the Future AGI project, removes
prompts, outputs, tool data and error text unless you opt in, and forwards to Future AGI with your keys.

    WXO_OTLP_ENDPOINT=http://localhost:4318/v1/traces OPENAI_API_KEY=... python agent.py "Weather in Paris?"

Environment: WXO_OTLP_ENDPOINT, OPENAI_API_KEY, OPENAI_BASE_URL (optional), MODEL [gpt-4.1-mini].
"""

import json
import os
import sys
import uuid

from ibm_watsonx_orchestrate_sdk.observability import Tracer, TracerConfig, register_tracer
from ibm_watsonx_orchestrate_sdk.observability.attributes import ATTR_INPUT, ATTR_OUTPUT
from ibm_watsonx_orchestrate_sdk.observability.decorators import (
    configure_tracing,
    trace_agent_call,
    trace_tool_call,
)
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

MODEL = os.environ.get("MODEL", "gpt-4.1-mini")

# One tracer per process. Without a Client, TracerConfig reads the OTLP endpoint from
# WXO_OTLP_ENDPOINT and sends no auth header: the collector adds the Future AGI keys.
tracer = Tracer(TracerConfig(service_name="weather-agent"))
register_tracer(tracer)

STATIONS = {"paris": "18 C, light rain", "tokyo": "24 C, clear", "lagos": "31 C, humid"}


@tool
@trace_tool_call(name="get_weather", tool_name="get_weather", capture_input=True, capture_output=True)
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    report = STATIONS.get(city.strip().lower())
    if report is None:
        raise ValueError(f"no weather station for {city}")
    return f"{city}: {report}"


llm = ChatOpenAI(model=MODEL, temperature=0).bind_tools([get_weather])


def call_model(messages):
    # The LLM span uses the context-manager form: @trace_llm_call records no token counts.
    with tracer.start_llm_span("chat_model", model=MODEL, provider="openai") as span:
        span.set_attribute(ATTR_INPUT, json.dumps([m.model_dump(mode="json") for m in messages]))
        reply = llm.invoke(messages)
        usage = reply.usage_metadata or {}
        span.record_completion(
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            response_model=reply.response_metadata.get("model_name"),
        )
        span.set_attribute(ATTR_OUTPUT, reply.model_dump_json())
        return reply


@trace_agent_call(name="agent_node", agent_name="weather-agent", framework="langgraph",
                  capture_input=True, capture_output=True)
def agent_node(state: MessagesState) -> dict:
    return {"messages": [call_model(state["messages"])]}


def route(state: MessagesState) -> str:
    return "tools" if state["messages"][-1].tool_calls else END


@configure_tracing
def create_agent(config: RunnableConfig):
    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode([get_weather], handle_tool_errors=True))  # a failed tool call goes back to the model
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, ["tools", END])
    graph.add_edge("tools", "agent")
    return graph.compile()


def ask(question: str, conversation_id: str | None = None) -> str:
    config: RunnableConfig = {"configurable": {}}
    agent = create_agent(config)
    # A root span per request keeps the agent, model and tool spans of one run in one trace.
    with tracer.start_root_span("weather-agent", attributes={"conversation.id": conversation_id or str(uuid.uuid4())}) as root:
        root.set_attribute(ATTR_INPUT, question)
        result = agent.invoke(
            {"messages": [SystemMessage("Use get_weather for weather questions. Answer in one sentence."),
                          HumanMessage(question)]},
            config,
        )
        answer = result["messages"][-1].content
        root.set_attribute(ATTR_OUTPUT, answer)
    return answer


if __name__ == "__main__":
    try:
        print(ask(" ".join(sys.argv[1:]) or "What is the weather in Paris?"))
    finally:
        tracer.shutdown()  # flushes the batch processor before the process exits
