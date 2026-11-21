import os
from contextlib import closing

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from openinference.instrumentation import TraceConfig
from traceai_agno import configure_agno_tracing


def lookup_care() -> str:
    """Look up the drying instructions for the Ridgeline rain shell."""
    return "Air dry away from direct heat."


base = os.getenv("FI_BASE_URL", "https://api.futureagi.com").rstrip("/")
tracing = configure_agno_tracing(
    otlp_endpoint=base + "/tracer/v1/traces",
    otlp_headers={"X-Api-Key": os.environ["FI_API_KEY"], "X-Secret-Key": os.environ["FI_SECRET_KEY"]},
    project_name="ridgeline-framework-tracing",
    config=TraceConfig(hide_inputs=True, hide_outputs=True),
)
try:
    agent = Agent(name="care-desk", model=OpenAIChat(id=os.environ["OPENAI_MODEL"]),
                  tools=[lookup_care], telemetry=False)
    with closing(agent.run("Use lookup_care to tell me how to dry my rain shell.", stream=True)) as events:
        for event in events:
            if isinstance(event.content, str):
                print(event.content, end="")
finally:
    tracing.uninstrument()
