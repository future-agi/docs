"""AgentCore order agent using Strands' native OTLP exporter.

Strands content redaction does not redact exception messages or stack traces.
Use the LangChain/traceAI example if you need its error-detail hiding controls.
"""

import logging
import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from opentelemetry.context import Context
from opentelemetry.trace import StatusCode
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from strands.telemetry import StrandsTelemetry

telemetry = StrandsTelemetry().setup_otlp_exporter()
provider = telemetry.tracer_provider
tracer = provider.get_tracer("order-agent")


@tool
def lookup_order(order_id: str) -> str:
    """Return the shipping status of an order such as A-100."""
    orders = {"A-100": "shipped", "A-200": "processing"}
    return f"order {order_id}: {orders.get(order_id, 'not found')}"


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    attributes = {"session.id": context.session_id} if context.session_id else {}
    try:
        with tracer.start_as_current_span(
            "agentcore.invocation", context=Context(),
            attributes={"fi.span.kind": "CHAIN", **attributes},
            record_exception=False, set_status_on_exception=False,
        ) as span:
            try:
                agent = Agent(
                    name="order_agent",
                    model=OpenAIModel(
                        client_args={"api_key": os.environ["OPENAI_API_KEY"],
                                     "base_url": os.environ.get("OPENAI_BASE_URL")},
                        model_id=os.environ.get("AGENT_MODEL", "gpt-4o-mini"),
                    ),
                    tools=[lookup_order],
                    system_prompt="Always call lookup_order for an order id.",
                    trace_attributes=attributes,
                    callback_handler=None,
                )
                return {"result": str(agent(payload.get("prompt", "")))}
            except Exception as exc:
                span.set_status(StatusCode.ERROR, type(exc).__name__)
                raise
    finally:
        try:
            if not provider.force_flush(timeout_millis=5000):
                logging.warning("Trace export timed out; some spans may be lost")
        except Exception:
            logging.warning("Trace export failed; some spans may be lost")


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
