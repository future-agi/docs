"""An Open Agent Spec agent with one tool, run on the LangGraph adapter, traced to Future AGI.

usage: python app.py [chat|async|tool-error|model-error] [question]

Environment
  FI_API_KEY, FI_SECRET_KEY        Future AGI keys (sent as X-Api-Key / X-Secret-Key)
  FI_BASE_URL                      collector origin, default https://api.futureagi.com
  FI_PROJECT_NAME                  Observe project, default open-agent-spec
  MODEL_BASE_URL, MODEL_API_KEY    any OpenAI-compatible Chat Completions endpoint
  MODEL_ID                         model id at that endpoint
  MODEL_BAD_API_KEY                key used by the model-error scenario (default: a dummy)
  FI_HIDE_INPUTS / FI_HIDE_OUTPUTS set to true to keep prompts, outputs and tool payloads out
  APP_RUNS                         run the agent this many times in one process (default 1)

Scenarios
  chat         one agent run that calls the tool (sync ``invoke``)
  async        the same run through ``ainvoke``
  tool-error   the tool raises; the run fails
  model-error  the model endpoint rejects the API key; the run fails
"""

from __future__ import annotations

import asyncio
import os
import sys

from futureagi_tracing import setup_tracing

# Tracing first, before the agent is loaded and run.
tracer_provider = setup_tracing(project_name=os.environ.get("FI_PROJECT_NAME", "open-agent-spec"))

import weather_agent  # noqa: E402

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "chat"
QUESTION = sys.argv[2] if len(sys.argv) > 2 else "What is the weather in Lisbon right now?"


def main() -> int:
    if SCENARIO == "tool-error":
        os.environ["WEATHER_TOOL_FAILS"] = "1"
    if SCENARIO == "model-error":
        api_key = os.environ.get("MODEL_BAD_API_KEY", "invalid-key-for-the-failure-case")
    else:
        api_key = os.environ["MODEL_API_KEY"]
    agent = weather_agent.load(api_key)
    request = {"messages": [{"role": "user", "content": QUESTION}]}
    try:
        for _ in range(int(os.environ.get("APP_RUNS", "1"))):
            if SCENARIO == "async":
                result = asyncio.run(agent.ainvoke(request))
            else:
                result = agent.invoke(request)
            print("RESULT ok:", result["messages"][-1].content)
        return 0
    except Exception as error:  # the failure scenarios end here
        print("RESULT error:", type(error).__name__)
        return 1
    finally:
        # Flush before the process exits (a short script would otherwise rely on atexit).
        tracer_provider.force_flush()


if __name__ == "__main__":
    sys.exit(main())
