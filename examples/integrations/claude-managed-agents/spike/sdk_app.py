"""Spike B: the anthropic Python SDK's own OpenTelemetry tracing for a Managed
Agents session, exported by the application straight to local Future AGI.

Real: anthropic SDK (tracing built in), opentelemetry-sdk, OTLP/HTTP exporter.
STANDIN: ANTHROPIC_BASE_URL points at sessions_stub.py, not api.anthropic.com.

The app does what Anthropic's SDK tracing page tells a customer to do:
register a tracer provider before the first call, export with OTLP, call the
SDK inside one of your own spans. Content mode is Anthropic's
ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE (default metadata_only).

  python sdk_app.py ok    -> one session: create, stream, list, send x2, custom tool
  python sdk_app.py fail  -> sessions.retrieve on an unknown session (404)
Prints the trace id. Env: ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY (any string for
the stub), FI_BASE_URL, FI_API_KEY, FI_SECRET_KEY, FI_PROJECT_NAME, MARKER.
"""
from __future__ import annotations

import asyncio
import os
import sys

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 1. Register a tracer provider before the first SDK call.
provider = TracerProvider(resource=Resource.create({
    "service.name": "managed-agents-app",
    "project_name": os.environ["FI_PROJECT_NAME"],
}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
    endpoint=os.environ["FI_BASE_URL"].rstrip("/") + "/v1/traces",
    headers={"X-Api-Key": os.environ["FI_API_KEY"], "X-Secret-Key": os.environ["FI_SECRET_KEY"]},
    compression=Compression.NoCompression,
)))
trace.set_tracer_provider(provider)

from anthropic import APIStatusError, AsyncAnthropic, beta_async_tool  # noqa: E402

MARKER = os.environ["MARKER"]
tracer = trace.get_tracer("managed-agents-app")


@beta_async_tool
async def count_files(pattern: str) -> str:
    """Count files matching a pattern.

    Args:
        pattern: glob pattern
    """
    return f"7 files match {pattern}"


async def ok(client: AsyncAnthropic) -> None:
    session = await client.beta.sessions.create(agent="agent_stub000000000000", environment_id="env_stub000000000000")
    runner = client.beta.sessions.events.tool_runner(session.id, tools=[count_files], max_idle=1.0)

    async def drive() -> None:
        async for call in runner:
            print("tool call dispatched:", call.event.name if hasattr(call, "event") else call)

    task = asyncio.create_task(drive())
    await asyncio.sleep(0.6)  # stream-first: the runner attaches before the message goes out
    await client.beta.sessions.events.send(
        session.id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": f"Count the files matching {MARKER}"}]}],
    )
    await asyncio.wait_for(task, timeout=30)


async def fail(client: AsyncAnthropic) -> None:
    try:
        await client.beta.sessions.retrieve("sesn_doesnotexist0000000000")
    except APIStatusError as e:
        print("expected failure:", e.status_code, type(e).__name__)


async def main(mode: str) -> None:
    client = AsyncAnthropic(max_retries=0)
    with tracer.start_as_current_span("managed-agent-run") as root:
        root.set_attribute("session.id", f"th8267-spike-{mode}")
        print("trace_id", format(root.get_span_context().trace_id, "032x"))
        await (ok if mode == "ok" else fail)(client)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ok"))
    provider.force_flush()
    provider.shutdown()
