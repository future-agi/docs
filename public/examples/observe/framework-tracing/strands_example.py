import os

from fi_instrumentation import register
from fi_instrumentation.fi_types import ProjectType
from fi_instrumentation.otel import HTTPSpanExporter
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from traceai_strands import StrandsSpanExporter


@tool
def lookup_care() -> str:
    """Look up the drying instructions for the Ridgeline rain shell."""
    return "Air dry away from direct heat."


provider = register(
    project_type=ProjectType.OBSERVE, project_name="ridgeline-framework-tracing",
    set_global_tracer_provider=True, span_exporter=StrandsSpanExporter(HTTPSpanExporter()), verbose=False,
)
try:
    agent = Agent(name="care-desk", model=OpenAIModel(model_id=os.environ["OPENAI_MODEL"]),
                  tools=[lookup_care], callback_handler=None)
    print(agent("Use lookup_care to tell me how to dry my rain shell."))
finally:
    provider.force_flush()
    provider.shutdown()
