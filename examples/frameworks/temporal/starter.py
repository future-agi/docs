"""Start one weather-agent workflow and print its answer.

    python starter.py "What is the weather in Lisbon today?" [--flaky] [--approval] [--id my-workflow-id]

Environment: see worker.py.
"""
import argparse
import asyncio
import os
import uuid

from temporalio.client import Client
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin

from tracing import setup_tracing
from workflows import TASK_QUEUE, AgentRequest, WeatherAgentWorkflow


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--id", default=f"weather-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--model", default=os.environ.get("MODEL", "gpt-6-luna"))
    parser.add_argument("--flaky", action="store_true")
    parser.add_argument("--approval", action="store_true", help="start and return: send the approve signal yourself")
    args = parser.parse_args()

    provider = setup_tracing(instrument_openai=False)
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        plugins=[OpenTelemetryPlugin(add_temporal_spans=True)],
    )
    request = AgentRequest(question=args.question, model=args.model, flaky=args.flaky, require_approval=args.approval)
    queue = os.environ.get("TASK_QUEUE", TASK_QUEUE)
    try:
        if args.approval:
            await client.start_workflow(WeatherAgentWorkflow.run, request, id=args.id, task_queue=queue)
            print(f"started {args.id}", flush=True)
        else:
            print(await client.execute_workflow(WeatherAgentWorkflow.run, request, id=args.id, task_queue=queue))
    finally:
        # A starter exits right after the call. Without this the StartWorkflow span is lost.
        provider.force_flush()
        provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
