#!/usr/bin/env python3
"""Deliberately wrong configurations, to show what each mistake does to the trace.

    python tools/negative.py worker-no-plugin            # a worker without OpenTelemetryPlugin
    python tools/negative.py starter "question" --no-plugin   # a starter without the plugin
    python tools/negative.py starter "question" --no-wait --os-exit    # starts and exits without flushing
    python tools/negative.py starter "question" --no-wait --os-exit --flush

The first: the model and tool spans are exported, but the workflow context never reaches the activity,
so they start new traces. The second: the workflow starts a trace of its own and the StartWorkflow
span does not exist. The third: spans still batched in the process are lost, because an exit through
os._exit(), a signal or a crash skips the exit hook that normally flushes them. --no-wait starts the
workflow and exits at once, like a request handler or a CLI; a starter that waits for the result usually
lives longer than the batch delay (5 s), so the batch has been exported by then and nothing is lost.
Environment: as worker.py. Run from the example directory, or anywhere: it imports the example modules.
"""
import argparse
import asyncio
import os
import signal
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from temporalio.client import Client  # noqa: E402
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from activities import get_weather, llm_answer, llm_plan  # noqa: E402
from tracing import setup_tracing  # noqa: E402
from workflows import TASK_QUEUE, AgentRequest, WeatherAgentWorkflow  # noqa: E402


def connect(plugins):
    return Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        plugins=plugins,
    )


async def worker_no_plugin() -> None:
    provider = setup_tracing()
    client = await connect([])
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    async with Worker(
        client,
        task_queue=os.environ.get("TASK_QUEUE", TASK_QUEUE),
        workflows=[WeatherAgentWorkflow],
        activities=[llm_plan, get_weather, llm_answer],
    ):
        print("worker ready", flush=True)
        await stop.wait()
    provider.force_flush()
    provider.shutdown()


async def starter(args: argparse.Namespace) -> None:
    provider = setup_tracing(instrument_openai=False)
    client = await connect([] if args.no_plugin else [OpenTelemetryPlugin(add_temporal_spans=True)])
    request = AgentRequest(question=args.question, model=args.model)
    queue = os.environ.get("TASK_QUEUE", TASK_QUEUE)
    if args.no_wait:
        await client.start_workflow(WeatherAgentWorkflow.run, request, id=args.id, task_queue=queue)
    else:
        print(await client.execute_workflow(WeatherAgentWorkflow.run, request, id=args.id, task_queue=queue), flush=True)
    if args.os_exit:
        if args.flush:
            provider.force_flush()
        os._exit(0)  # skips atexit: nothing that is still batched is exported
    provider.force_flush()
    provider.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("worker-no-plugin")
    s = sub.add_parser("starter")
    s.add_argument("question")
    s.add_argument("--id", default=f"weather-{uuid.uuid4().hex[:12]}")
    s.add_argument("--model", default=os.environ.get("MODEL", "gpt-6-luna"))
    s.add_argument("--no-plugin", action="store_true")
    s.add_argument("--no-wait", action="store_true", help="start the workflow and do not wait for its result")
    s.add_argument("--os-exit", action="store_true")
    s.add_argument("--flush", action="store_true")
    args = parser.parse_args()
    asyncio.run(worker_no_plugin() if args.cmd == "worker-no-plugin" else starter(args))


if __name__ == "__main__":
    main()
