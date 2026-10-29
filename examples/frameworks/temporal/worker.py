"""Temporal worker for the weather agent, traced to Future AGI.

    python worker.py

Environment: see tracing.py, plus OPENAI_API_KEY / OPENAI_BASE_URL for the model, and
    TEMPORAL_ADDRESS            default localhost:7233
    TEMPORAL_NAMESPACE          default "default"
    TASK_QUEUE                  default "weather-agent"
    MAX_CACHED_WORKFLOWS        default 1000; 0 makes every workflow task replay the history
"""
import asyncio
import os
import signal

from temporalio.client import Client
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin
from temporalio.worker import Worker

from activities import get_weather, llm_answer, llm_plan
from tracing import setup_tracing
from workflows import TASK_QUEUE, WeatherAgentWorkflow


async def main() -> None:
    provider = setup_tracing()
    # The plugin goes on the client. A worker built from that client gets it too.
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        plugins=[OpenTelemetryPlugin(add_temporal_spans=True)],
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    worker = Worker(
        client,
        task_queue=os.environ.get("TASK_QUEUE", TASK_QUEUE),
        workflows=[WeatherAgentWorkflow],
        activities=[llm_plan, get_weather, llm_answer],
        max_cached_workflows=int(os.environ.get("MAX_CACHED_WORKFLOWS", "1000")),
    )
    async with worker:
        print("worker ready", flush=True)
        await stop.wait()
    provider.force_flush()  # spans of the last activities and workflows are still batched
    provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
