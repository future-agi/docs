"""Comparison only: the same agent traced with Arize's ``openinference-instrumentation-agentspec``
(a third-party package, not maintained by Future AGI and not in requirements.txt) on the
Future AGI tracer provider. The page's "Arize's Agent Spec instrumentor" section is based on
runs of this script. Do not combine it with app.py's LangChain instrumentor.

usage: pip install openinference-instrumentation-agentspec==0.1.15
       python scripts/openinference_variant.py [chat|tool-error|model-error] [question]

Masking: Arize's instrumentor exports content unless ``mask_sensitive_information=True``.
This script masks when FI_HIDE_INPUTS or FI_HIDE_OUTPUTS is true, like app.py hides.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fi_instrumentation import register  # noqa: E402
from fi_instrumentation.fi_types import ProjectType  # noqa: E402
from openinference.instrumentation.agentspec import AgentSpecInstrumentor  # noqa: E402

_TRUE = {"1", "true", "yes", "on"}
mask = any(os.environ.get(v, "").lower() in _TRUE for v in ("FI_HIDE_INPUTS", "FI_HIDE_OUTPUTS"))

os.environ.setdefault("FI_PROJECT_NAME", "open-agent-spec-openinference")
# The two calls shown on the page:
tracer_provider = register(project_type=ProjectType.OBSERVE)
AgentSpecInstrumentor().instrument(tracer_provider=tracer_provider, mask_sensitive_information=mask)

import weather_agent  # noqa: E402

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "chat"
QUESTION = sys.argv[2] if len(sys.argv) > 2 else "What is the weather in Lisbon right now?"

if SCENARIO == "tool-error":
    os.environ["WEATHER_TOOL_FAILS"] = "1"
key = (os.environ.get("MODEL_BAD_API_KEY", "invalid-key-for-the-failure-case")
       if SCENARIO == "model-error" else os.environ["MODEL_API_KEY"])
agent = weather_agent.load(key)
code = 0
try:
    for _ in range(int(os.environ.get("APP_RUNS", "1"))):
        result = agent.invoke({"messages": [{"role": "user", "content": QUESTION}]})
        print("RESULT ok:", result["messages"][-1].content)
except Exception as error:
    print("RESULT error:", type(error).__name__)
    code = 1
finally:
    # The instrumentor's Agent Spec RootSpan only ends (and exports) here.
    AgentSpecInstrumentor().uninstrument()
    tracer_provider.force_flush()
sys.exit(code)
