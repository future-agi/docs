"""A LangChain agent hosted in Amazon Bedrock AgentCore Runtime, traced to Future AGI.

Run locally (the same process AgentCore runs in its container):

    python agent_langchain.py          # serves POST /invocations and GET /ping on :8080

Environment (set them on the AgentCore runtime with `agentcore launch --env ...`, keys from a
secret store, never in the image):

    DISABLE_ADOT_OBSERVABILITY=true    # AgentCore: do not set up ADOT (see the docs page)
    FI_API_KEY, FI_SECRET_KEY          # Future AGI keys
    FI_BASE_URL                        # optional, default https://api.futureagi.com
    FI_PROJECT_NAME                    # the Observe project
    OPENAI_API_KEY, OPENAI_BASE_URL    # any OpenAI-compatible endpoint for this example
    AGENT_MODEL                        # model id, default gpt-4o-mini
    JOIN_CALLER_TRACE=true             # optional: only when the caller exports to the same project
"""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from fi_instrumentation import register
from fi_instrumentation.fi_types import ProjectType
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from traceai_langchain import LangChainInstrumentor

import agentcore_tracing

# 1. Future AGI first: provider, instrumentor, then keep the exporter attached once AgentCore
#    adds its BaggageSpanProcessor to the global provider.
provider = register(
    project_type=ProjectType.OBSERVE,
    project_name=os.environ.get("FI_PROJECT_NAME", "bedrock-agentcore-agent"),
    set_global_tracer_provider=True,
    verbose=False,
)
agentcore_tracing.keep_future_agi_exporter(provider)
LangChainInstrumentor().instrument(tracer_provider=provider)

# Adopt the caller's traceparent as parent only when the caller's spans also reach this Future AGI
# project; otherwise the root span links to the caller and starts its own (listed) trace.
JOIN_CALLER_TRACE = os.environ.get("JOIN_CALLER_TRACE", "false").lower() == "true"

ORDERS = {"A-100": "shipped", "A-200": "processing"}


@tool
def lookup_order(order_id: str) -> str:
    """Return the shipping status of an order id such as A-100."""
    return f"order {order_id}: {ORDERS.get(order_id, 'not found')}"


agent = create_agent(
    ChatOpenAI(model=os.environ.get("AGENT_MODEL", "gpt-4o-mini"), temperature=0),
    tools=[lookup_order],
    system_prompt="You answer questions about orders. Always call lookup_order for an order id.",
    name="order_agent",
)

# 2. The AgentCore app. Constructing it registers AgentCore's BaggageSpanProcessor.
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    # 3. One root span per invocation: caller trace, session id, flush on success and on error.
    with agentcore_tracing.traced_invocation(context, provider, join_caller_trace=JOIN_CALLER_TRACE):
        result = agent.invoke({"messages": [{"role": "user", "content": payload.get("prompt", "")}]})
        return {"result": result["messages"][-1].content}


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
