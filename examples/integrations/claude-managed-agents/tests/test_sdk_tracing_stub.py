"""Offline: the real anthropic SDK's own tracing for a Managed Agents session,
against the local Sessions API stub (STANDIN), captured in memory.

Checks what the page says about SDK tracing: request spans + the tool runner's
custom tool span, no turn / model-request / token spans, metadata only by
default, tool payloads only with ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content,
ERROR on a failed request.

Run: python -I tests/test_sdk_tracing_stub.py   (needs requirements.txt; skips without anthropic)
"""
import asyncio
import os
import pathlib
import socket
import subprocess
import sys
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPIKE = HERE.parent / "spike"

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    import anthropic  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

MARK = "SDKUNITMARKER42"
CONTENT_KEYS = {"gen_ai.tool.call.arguments", "anthropic.tool_result.content"}

if HAVE:
    EXPORTER = InMemorySpanExporter()
    _provider = TracerProvider()
    _provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
    trace.set_tracer_provider(_provider)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def run_session(base_url, content):
    from anthropic import AsyncAnthropic, beta_async_tool

    @beta_async_tool
    async def count_files(pattern: str) -> str:
        """Count files matching a pattern.

        Args:
            pattern: glob pattern
        """
        return f"7 files match {pattern}"

    opts = {"traces": {"content_mode": "content"}} if content else {}
    client = AsyncAnthropic(base_url=base_url, api_key="stub-not-a-key", max_retries=0,
                            **({"open_telemetry": opts} if content else {}))
    with trace.get_tracer("t").start_as_current_span("root"):
        s = await client.beta.sessions.create(agent="agent_stub000000000000", environment_id="env_stub0000")
        runner = client.beta.sessions.events.tool_runner(s.id, tools=[count_files], max_idle=0.5)

        async def drive():
            async for _ in runner:
                pass
        task = asyncio.create_task(drive())
        await asyncio.sleep(0.5)
        await client.beta.sessions.events.send(
            s.id, events=[{"type": "user.message", "content": [{"type": "text", "text": f"count {MARK}"}]}])
        await asyncio.wait_for(task, timeout=20)
        try:
            await client.beta.sessions.retrieve("sesn_missing000000000000")
        except Exception:
            pass
    await client.close()


@unittest.skipUnless(HAVE, "anthropic / opentelemetry-sdk not installed")
class SdkTracing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.proc = subprocess.Popen([sys.executable, "-I", str(SPIKE / "sessions_stub.py"), str(cls.port)],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cls.proc.stdout.readline()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)

    def spans(self, content):
        EXPORTER.clear()
        os.environ.pop("ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE", None)
        asyncio.run(run_session(f"http://127.0.0.1:{self.port}", content))
        return [s for s in EXPORTER.get_finished_spans() if s.name != "root"]

    def test_default_is_metadata_only(self):
        spans = self.spans(content=False)
        names = {s.name for s in spans}
        for n in ("anthropic.sessions.create", "anthropic.sessions.events.send", "anthropic.sessions.events.stream",
                  "anthropic.sessions.events.list", "anthropic.custom_tool_use count_files",
                  "anthropic.sessions.retrieve"):
            self.assertIn(n, names)
        # API-only spans never come from the SDK
        self.assertFalse(names & {"anthropic.session.turn", "anthropic.model_request"})
        for s in spans:
            self.assertFalse(any("usage" in k for k in s.attributes), s.name)
            self.assertFalse(CONTENT_KEYS & set(s.attributes), s.name)
            self.assertNotIn(MARK, repr(dict(s.attributes)))
            self.assertNotIn("stub-not-a-key", repr(dict(s.attributes)))
        create = next(s for s in spans if s.name == "anthropic.sessions.create")
        self.assertEqual(create.kind, trace.SpanKind.CLIENT)
        self.assertEqual(create.attributes["gen_ai.request.model"], "claude-opus-5-5")

    def test_content_mode_adds_tool_payloads_only(self):
        spans = self.spans(content=True)
        with_mark = {s.name: sorted(k for k, v in s.attributes.items() if MARK in str(v)) for s in spans
                     if MARK in repr(dict(s.attributes))}
        self.assertEqual(with_mark, {"anthropic.custom_tool_use count_files": sorted(CONTENT_KEYS)})

    def test_failed_request_is_error(self):
        spans = self.spans(content=False)
        bad = next(s for s in spans if s.name == "anthropic.sessions.retrieve")
        self.assertEqual(bad.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(bad.attributes["error.type"], "not_found_error")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
