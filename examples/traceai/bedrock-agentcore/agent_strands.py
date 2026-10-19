"""A Strands agent hosted in Amazon Bedrock AgentCore Runtime, traced to Future AGI with plain OTLP.

Strands has its own OpenTelemetry tracer. This example does not use a traceAI instrumentor: it
points Strands' OTLP exporter at Future AGI with the standard OTEL_EXPORTER_OTLP_* variables.

Run locally (the same process AgentCore runs in its container):

    python agent_strands.py            # serves POST /invocations and GET /ping on :8080

Environment (set them on the AgentCore runtime with `agentcore launch --env ...`):

    DISABLE_ADOT_OBSERVABILITY=true
    OTEL_EXPORTER_OTLP_ENDPOINT=https://api.futureagi.com      # origin only; /v1/traces is appended
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
    OTEL_EXPORTER_OTLP_HEADERS=X-Api-Key=<key>,X-Secret-Key=<secret>
    OTEL_RESOURCE_ATTRIBUTES=project_name=<project>,project_type=observe
    # content off: Strands redacts prompts, responses, tool arguments and results
    OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental,gen_ai_span_attributes_only,gen_ai_unredacted_attributes=
    OPENAI_API_KEY, OPENAI_BASE_URL, AGENT_MODEL                  # model for this example
    JOIN_CALLER_TRACE=true            # optional: only when the caller exports to the same project

Content opt-in: drop the `gen_ai_unredacted_attributes=` token (keep the other two, so Strands
writes messages as span attributes, which Future AGI stores, instead of span events).
"""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from strands.telemetry import StrandsTelemetry

import agentcore_tracing

# 1. Strands' own provider (set as the global provider). The OTLP exporter reads
#    OTEL_EXPORTER_OTLP_*. Error spans never carry a stack trace; with content off they keep
#    only the exception type name.
telemetry = StrandsTelemetry()
provider = telemetry.tracer_provider
exporter = agentcore_tracing.ErrorTextExporter(
    OTLPSpanExporter(), type_only=agentcore_tracing.strands_redaction_enabled()
)
provider.add_span_processor(BatchSpanProcessor(exporter))
# Stamp only session.id from OpenTelemetry baggage on every Strands span.
telemetry.setup_baggage_processor(lambda key: key == agentcore_tracing.SESSION_ATTRIBUTE)

# Adopt the caller's traceparent as parent only when the caller's spans also reach this Future AGI
# project; otherwise the root span links to the caller and starts its own (listed) trace.
JOIN_CALLER_TRACE = os.environ.get("JOIN_CALLER_TRACE", "false").lower() == "true"

ORDERS = {"A-100": "shipped", "A-200": "processing"}


@tool
def lookup_order(order_id: str) -> str:
    """Return the shipping status of an order id such as A-100."""
    return f"order {order_id}: {ORDERS.get(order_id, 'not found')}"


def make_agent() -> Agent:
    model = OpenAIModel(
        client_args={"api_key": os.environ.get("OPENAI_API_KEY"), "base_url": os.environ.get("OPENAI_BASE_URL")},
        model_id=os.environ.get("AGENT_MODEL", "gpt-4o-mini"),
    )
    return Agent(
        name="order_agent",
        model=model,
        tools=[lookup_order],
        system_prompt="You answer questions about orders. Always call lookup_order for an order id.",
        callback_handler=None,
    )


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    with agentcore_tracing.traced_invocation(context, provider, join_caller_trace=JOIN_CALLER_TRACE):
        result = make_agent()(payload.get("prompt", ""))
        return {"result": str(result)}


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")))
