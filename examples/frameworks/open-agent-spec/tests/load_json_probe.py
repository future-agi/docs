"""Probe for test_load_json.py: the same agent, serialized to Agent Spec JSON and loaded back
with ``AgentSpecLoader.load_json``, traced with ``setup_tracing()``. Prints the JSON's facts."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from futureagi_tracing import setup_tracing  # noqa: E402

tracer_provider = setup_tracing()

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
