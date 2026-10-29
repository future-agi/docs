#!/usr/bin/env python3
"""Replay the stored history of a finished workflow, with tracing on, and report what was exported.

    python tools/replay_check.py WORKFLOW_ID

Fetches the workflow's history from the Temporal server and runs it through temporalio's Replayer with
the same tracer provider and plugin as the worker. The Replayer re-executes the workflow code from the
first event, so every span the workflow creates is created again. Replay-safe spans are not ended
while replaying, so nothing is exported: pair this with wire_tap.py and wire_check.py, or compare the
span count of the workflow in Future AGI before and after.
Environment: as worker.py.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from temporalio.client import Client  # noqa: E402
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin  # noqa: E402
from temporalio.worker import Replayer  # noqa: E402

from tracing import setup_tracing  # noqa: E402
from workflows import WeatherAgentWorkflow  # noqa: E402


async def main(workflow_id: str) -> None:
    provider = setup_tracing(instrument_openai=False)
    plugin = OpenTelemetryPlugin(add_temporal_spans=True)
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        plugins=[plugin],
    )
    history = await client.get_workflow_handle(workflow_id).fetch_history()
    await Replayer(workflows=[WeatherAgentWorkflow], plugins=[plugin]).replay_workflow(history)
    provider.force_flush()
    provider.shutdown()
    print(f"replayed {len(history.events)} history events of {workflow_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
