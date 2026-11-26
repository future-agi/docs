"""Probe for test_load_json.py: the same agent, serialized to Agent Spec JSON and loaded back
with ``AgentSpecLoader.load_json``, traced with the maintained APIs. Prints the JSON's facts."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fi_instrumentation import TraceConfig, register  # noqa: E402
from fi_instrumentation.fi_types import ProjectType  # noqa: E402
from traceai_langchain import LangChainInstrumentor  # noqa: E402

tracer_provider = register(project_type=ProjectType.OBSERVE, verbose=False)
LangChainInstrumentor().instrument(
    tracer_provider=tracer_provider,
    config=TraceConfig(hide_error_details=True),
)

import weather_agent  # noqa: E402
from pyagentspec.adapters.langgraph import AgentSpecLoader  # noqa: E402
from pyagentspec.serialization import AgentSpecSerializer  # noqa: E402

key = os.environ["MODEL_API_KEY"]
agent = weather_agent.build_agent(key)
text = AgentSpecSerializer().to_json(agent)
graph = AgentSpecLoader(tool_registry={"get_weather": weather_agent.get_weather}).load_json(
    text, components_registry={f"{agent.llm_config.id}.api_key": key}
)
graph.invoke({"messages": [{"role": "user", "content": "What is the weather in Lisbon?"}]})
tracer_provider.force_flush()
print(json.dumps({"key_in_json": key in text, "component_ref": "$component_ref" in text}))
