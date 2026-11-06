"""A weather agent as a Temporal workflow.

Workflow code must stay deterministic and must not import an exporter, an HTTP client or the model
SDK: the activities do all of that. This module imports only `temporalio` and the standard library,
and refers to activities by name, so the workflow sandbox loads it without passthrough rules.
"""
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "weather-agent"
SYSTEM_PROMPT = "Use the get_weather tool, then answer in one sentence."


@dataclass
class AgentRequest:
    question: str
    model: str = "gpt-6-luna"
    flaky: bool = False  # the first weather lookup fails, so Temporal retries the activity
    require_approval: bool = False  # wait for the `approve` signal before the tool runs


@workflow.defn
class WeatherAgentWorkflow:
    def __init__(self) -> None:
        self._approved = False

    @workflow.signal
    def approve(self) -> None:
        self._approved = True

    @workflow.run
    async def run(self, req: AgentRequest) -> str:
        retry = RetryPolicy(initial_interval=timedelta(milliseconds=200), maximum_attempts=2)
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.question},
        ]
        plan = await workflow.execute_activity(
            "llm_plan", args=[req.model, messages], start_to_close_timeout=timedelta(seconds=60), retry_policy=retry
        )
        messages.append(plan)
        if req.require_approval:
            await workflow.wait_condition(lambda: self._approved)
        for call in plan["tool_calls"]:
            result = await workflow.execute_activity(
                "get_weather",
                args=[call["function"]["arguments"], req.flaky],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        final = await workflow.execute_activity(
            "llm_answer", args=[req.model, messages], start_to_close_timeout=timedelta(seconds=60), retry_policy=retry
        )
        return final["content"]
