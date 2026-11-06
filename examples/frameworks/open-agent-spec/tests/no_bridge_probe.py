"""Probe for test_no_bridge.py: run the LangGraph adapter with a global OpenTelemetry tracer
provider and NO instrumentor, and report what OpenTelemetry received versus what the
pyagentspec span bus carried. usage: no_bridge_probe.py MODEL_URL MODEL_KEY"""

import json
import sys

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

memory = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(memory))
trace.set_tracer_provider(provider)

from pyagentspec.adapters.langgraph import AgentSpecLoader  # noqa: E402
from pyagentspec.agent import Agent  # noqa: E402
from pyagentspec.llms import OpenAiCompatibleConfig  # noqa: E402
from pyagentspec.property import StringProperty  # noqa: E402
from pyagentspec.tools import ServerTool  # noqa: E402
from pyagentspec.tracing.spanprocessor import SpanProcessor  # noqa: E402
from pyagentspec.tracing.trace import Trace  # noqa: E402

bus = []


class BusRecorder(SpanProcessor):
    def on_start(self, span): ...
    async def on_start_async(self, span): ...
    def on_end(self, span):
        tokens = [
            [getattr(e, "input_tokens", None), getattr(e, "output_tokens", None)]
            for e in span.events
            if type(e).__name__ == "LlmGenerationResponse"
        ]
        bus.append({"type": type(span).__name__, "name": span.name, "tokens": tokens})
    async def on_end_async(self, span):
        self.on_end(span)
    def on_event(self, event, span): ...
    async def on_event_async(self, event, span): ...
    def startup(self): ...
    async def startup_async(self): ...
    def shutdown(self): ...
    async def shutdown_async(self): ...


agent = Agent(
    name="weather_assistant",
    llm_config=OpenAiCompatibleConfig(name="m", url=sys.argv[1], model_id="fake-model", api_key=sys.argv[2]),
    tools=[ServerTool(name="get_weather", description="Weather.", inputs=[StringProperty(title="city")],
                      outputs=[StringProperty(title="forecast")])],
    system_prompt="Call get_weather.",
)
graph = AgentSpecLoader(tool_registry={"get_weather": lambda city: f"Sunny in {city}"}).load_component(agent)
with Trace(name="probe", span_processors=[BusRecorder()]):
    graph.invoke({"messages": [{"role": "user", "content": "Weather in Lisbon?"}]})
provider.force_flush()
print(json.dumps({"otel": [s.name for s in memory.get_finished_spans()], "bus": bus}))
