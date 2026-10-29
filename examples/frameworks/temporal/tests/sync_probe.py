"""A workflow with one synchronous (thread pool) and one asynchronous activity, for the context test."""
from datetime import timedelta

from opentelemetry import trace
from temporalio import activity, workflow


@activity.defn
def sync_activity(text: str) -> str:
    with trace.get_tracer("probe").start_as_current_span("inside-sync-activity"):
        return text


@activity.defn
async def async_activity(text: str) -> str:
    with trace.get_tracer("probe").start_as_current_span("inside-async-activity"):
        return text


@workflow.defn
class ProbeWorkflow:
    @workflow.run
    async def run(self) -> str:
        await workflow.execute_activity("sync_activity", "a", start_to_close_timeout=timedelta(seconds=10))
        return await workflow.execute_activity("async_activity", "a", start_to_close_timeout=timedelta(seconds=10))
