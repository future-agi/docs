"""AgentCore order agent using released traceAI packages; no tracing helper."""

import logging
import os
from contextlib import nullcontext

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from fi_instrumentation import FITracer, TraceConfig, register, using_session
from fi_instrumentation.fi_types import ProjectType
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from opentelemetry.context import Context
from traceai_langchain import LangChainInstrumentor

# Read FI_HIDE_* once at startup, and use the same policy for framework and app spans.
config = TraceConfig()
provider = register(
    project_type=ProjectType.OBSERVE,
    project_name=os.environ.get("FI_PROJECT_NAME", "bedrock-agentcore-agent"),
    set_global_tracer_provider=True,
    verbose=False,
)
LangChainInstrumentor().instrument(tracer_provider=provider, config=config)
tracer = FITracer(provider.get_tracer("order-agent"), config=config)


@tool
def lookup_order(order_id: str) -> str:
    """Return the shipping status of an order such as A-100."""
    orders = {"A-100": "shipped", "A-200": "processing"}
    return f"order {order_id}: {orders.get(order_id, 'not found')}"


agent = create_agent(
    ChatOpenAI(model=os.environ.get("AGENT_MODEL", "gpt-4o-mini"), temperature=0),
    tools=[lookup_order],
    system_prompt="You answer questions about orders. Always call lookup_order for an order id.",
    name="order_agent",
)
app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    try:
        session = using_session(context.session_id) if context.session_id else nullcontext()
        with session, tracer.start_as_current_span(
            "agentcore.invocation", context=Context(), fi_span_kind="chain"
        ):
            result = agent.invoke({"messages": [{"role": "user", "content": payload.get("prompt", "")}]})
            return {"result": result["messages"][-1].content}
    finally:
        # End the root first; a batch timer may not fire before the runtime idles.
        try:
            if not provider.force_flush(timeout_millis=5000):
                logging.warning("Trace export timed out; some spans may be lost")
        except Exception:
            logging.warning("Trace export failed; some spans may be lost")


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
