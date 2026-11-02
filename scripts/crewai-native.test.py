"""Native CrewAI contract tests. Synthetic credentials and loopback HTTP only.

Run with pytest inside a network-denied sandbox (loopback allowed). No traceAI
instrumentor, patched LLM methods, or real provider credentials are used.
"""

import asyncio
import errno
import json
import os
import re
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from google.protobuf.json_format import MessageToDict
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.resources import Resource

# Set before imports: product analytics and CrewAI-hosted tracing are independent
# of the explicitly owned native OTLP session below.
os.environ.update(
    CREWAI_DISABLE_TELEMETRY="true",
    CREWAI_DISABLE_TRACKING="true",
    CREWAI_TRACING_ENABLED="false",
    OTEL_SDK_DISABLED="false",
    OPENAI_API_KEY="synthetic-openai-config-canary",
)

from crewai import Agent, Crew, LLM, Task
from crewai.events import crewai_event_bus
from crewai.flow.flow import Flow, listen, start
from crewai.telemetry.tracing import telemetry_session


class LocalServer:
    """Collect OTLP protobuf and serve deterministic OpenAI completions."""

    def __init__(self):
        self.spans = []
        self.resources = []
        self.headers = []
        self.prompts = []
        self.fail = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path == "/tracer/v1/traces":
                    request = ExportTraceServiceRequest.FromString(body)
                    data = MessageToDict(request)
                    owner.headers.append(dict(self.headers))
                    for resource in data["resourceSpans"]:
                        owner.resources.append(attrs(resource["resource"]))
                        for scope in resource["scopeSpans"]:
                            owner.spans.extend(scope["spans"])
                    response = b""
                    status = 200
                elif self.path == "/v1/chat/completions":
                    owner.prompts.append(json.loads(body))
                    if owner.fail:
                        response = json.dumps(
                            {
                                "error": {
                                    "message": "synthetic model failure",
                                    "type": "invalid_request_error",
                                }
                            }
                        ).encode()
                        status = 400
                    else:
                        response = json.dumps(
                            {
                                "id": "synthetic-completion",
                                "object": "chat.completion",
                                "created": 1,
                                "model": "gpt-4o-mini",
                                "choices": [
                                    {
                                        "index": 0,
                                        "message": {
                                            "role": "assistant",
                                            "content": "Final Answer: Useful answer",
                                        },
                                        "finish_reason": "stop",
                                    }
                                ],
                                "usage": {
                                    "prompt_tokens": 11,
                                    "completion_tokens": 5,
                                    "total_tokens": 16,
                                },
                            }
                        ).encode()
                        status = 200
                else:
                    self.send_error(404)
                    return
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *_args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.http.server_port}"
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()


def attrs(span):
    return {
        item["key"]: next(iter(item["value"].values()))
        for item in span.get("attributes", [])
    }


@pytest.fixture
def server():
    value = LocalServer()
    try:
        yield value
    finally:
        value.close()


@contextmanager
def session(server):
    exporter = OTLPSpanExporter(
        endpoint=server.origin + "/tracer/v1/traces",
        headers={
            "X-Api-Key": "synthetic-fi-key",
            "X-Secret-Key": "synthetic-fi-secret",
        },
    )
    with telemetry_session(
        str(uuid4()),
        "crewai_project",
        exporters=[exporter],
        resource=Resource(
            {
                "service.name": "crewai-app",
                "project_name": "crewai_project",
                "project_type": "observe",
            }
        ),
    ):
        yield


def agent(server):
    llm = LLM(
        model="openai/gpt-4o-mini",
        base_url=server.origin + "/v1",
        api_key=os.environ["OPENAI_API_KEY"],
    )
    return Agent(
        role="Writer",
        goal="Write a useful answer",
        backstory="A concise writer",
        llm=llm,
        allow_delegation=False,
    )


class ExampleFlow(Flow):
    @start()
    def prepare(self):
        return "Useful input"

    @listen(prepare)
    def finish(self, text):
        return text + " and output"


def assert_transport(server):
    assert server.spans
    assert len({s["spanId"] for s in server.spans}) == len(server.spans)
    assert all(
        int(s["endTimeUnixNano"]) >= int(s["startTimeUnixNano"]) > 0
        for s in server.spans
    )
    for headers in server.headers:
        lowered = {k.lower(): v for k, v in headers.items()}
        assert lowered["x-api-key"] == "synthetic-fi-key"
        assert lowered["x-secret-key"] == "synthetic-fi-secret"
        assert lowered["content-type"] == "application/x-protobuf"
    assert all(
        r["project_name"] == "crewai_project" and r["project_type"] == "observe"
        for r in server.resources
    )
    # Configuration credentials stay in HTTP headers, not span content.
    payload = json.dumps(server.spans)
    for canary in (
        "synthetic-openai-config-canary",
        "synthetic-fi-key",
        "synthetic-fi-secret",
    ):
        assert canary not in payload


def test_outbound_network_is_denied():
    with socket.socket() as connection:
        connection.settimeout(1)
        with pytest.raises(OSError) as error:
            connection.connect(("192.0.2.1", 443))
        assert error.value.errno in (errno.EPERM, errno.EACCES, errno.ENETUNREACH)


def test_native_flow_sync_and_async(server):
    for async_run in (False, True):
        start_index = len(server.spans)
        with session(server):
            flow = ExampleFlow()
            result = asyncio.run(flow.kickoff_async()) if async_run else flow.kickoff()
        assert result == "Useful input and output"
        spans = server.spans[start_index:]
        roots = [
            s
            for s in spans
            if attrs(s).get("gen_ai.operation.name") == "invoke_workflow"
        ]
        methods = [
            s
            for s in spans
            if attrs(s).get("gen_ai.operation.name") == "execute_method"
        ]
        assert len(roots) == 1 and len(methods) == 2
        assert len(spans) == 3
        assert all(
            s["parentSpanId"] == roots[0]["spanId"]
            and s["traceId"] == roots[0]["traceId"]
            for s in methods
        )
        assert "Useful input and output" in attrs(roots[0])["gen_ai.output.messages"]
    assert_transport(server)


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("async_run", [False, True])
def test_native_agent_and_model(server, standalone, async_run):
    with session(server):
        writer = agent(server)
        if standalone:
            result = (
                asyncio.run(writer.kickoff_async("Write a useful answer"))
                if async_run
                else writer.kickoff("Write a useful answer")
            )
        else:
            task = Task(
                description="Write a useful answer",
                expected_output="One sentence",
                agent=writer,
            )
            crew = Crew(agents=[writer], tasks=[task])
            result = asyncio.run(crew.kickoff_async()) if async_run else crew.kickoff()
    assert "Useful answer" in result.raw
    assert len(server.prompts) == 1
    llms = [s for s in server.spans if attrs(s).get("gen_ai.operation.name") == "chat"]
    agents = [
        s
        for s in server.spans
        if attrs(s).get("gen_ai.operation.name") == "invoke_agent"
    ]
    assert len(llms) == len(agents) == 1
    assert llms[0]["parentSpanId"] == agents[0]["spanId"]
    if not standalone:
        crews = [
            s
            for s in server.spans
            if attrs(s).get("gen_ai.operation.name") == "invoke_workflow"
        ]
        tasks = [
            s
            for s in server.spans
            if attrs(s).get("gen_ai.operation.name") == "execute_task"
        ]
        assert len(crews) == len(tasks) == 1
        assert tasks[0]["parentSpanId"] == crews[0]["spanId"]
        assert agents[0]["parentSpanId"] == tasks[0]["spanId"]
    assert len({s["traceId"] for s in server.spans}) == 1
    values = attrs(llms[0])
    assert values["gen_ai.request.model"] == "gpt-4o-mini"
    assert values["gen_ai.provider.name"] == "openai"
    assert int(values["gen_ai.usage.input_tokens"]) == 11
    assert int(values["gen_ai.usage.output_tokens"]) == 5
    assert "Write a useful answer" in values["gen_ai.input.messages"]
    assert "Useful answer" in values["gen_ai.output.messages"]
    assert_transport(server)


def test_native_model_failure_closes_span(server):
    server.fail = True
    with pytest.raises(Exception, match="synthetic model failure"):
        with session(server):
            agent(server).llm.call("Write a useful answer")
    llms = [s for s in server.spans if attrs(s).get("gen_ai.operation.name") == "chat"]
    assert len(llms) == 1
    assert llms[0]["status"]["code"] == "STATUS_CODE_ERROR"
    assert_transport(server)


def test_native_flow_failure_and_session_cleanup(server):
    class BrokenFlow(Flow):
        @start()
        def fail(self):
            raise ValueError("synthetic flow failure")

    with pytest.raises(ValueError, match="synthetic flow failure"):
        with session(server):
            BrokenFlow().kickoff()
    assert len(server.spans) == 2
    assert all(s["status"]["code"] == "STATUS_CODE_ERROR" for s in server.spans)
    count = len(server.spans)
    ExampleFlow().kickoff()
    crewai_event_bus.flush(timeout=10)
    assert len(server.spans) == count  # The closed session no longer listens.
    assert_transport(server)


def test_overlapping_sessions_keep_distinct_traces(server):
    class AsyncFlow(Flow):
        @start()
        async def prepare(self):
            await asyncio.sleep(0.02)
            return "Useful output"

    async def run_one():
        with session(server):
            return await AsyncFlow().kickoff_async()

    async def run_both():
        return await asyncio.gather(run_one(), run_one())

    assert asyncio.run(run_both()) == ["Useful output", "Useful output"]
    assert len(server.spans) == 4
    roots = [
        s
        for s in server.spans
        if attrs(s).get("gen_ai.operation.name") == "invoke_workflow"
    ]
    assert len(roots) == 2
    assert len({s["traceId"] for s in roots}) == 2
    for root in roots:
        children = [s for s in server.spans if s.get("parentSpanId") == root["spanId"]]
        assert len(children) == 1 and children[0]["traceId"] == root["traceId"]
    assert_transport(server)


def test_documented_python_snippets(server, monkeypatch):
    page = (
        Path(__file__).parent.parent / "src/pages/docs/integrations/traceai/crewai.mdx"
    ).read_text()
    snippets = re.findall(r"```python\n(.*?)```", page, re.S)
    assert len(snippets) == 2
    monkeypatch.setenv("FI_API_KEY", "synthetic-fi-key")
    monkeypatch.setenv("FI_SECRET_KEY", "synthetic-fi-secret")
    monkeypatch.setenv("OPENAI_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", server.origin + "/v1")
    # The only code substitution is the collector destination. The documented
    # credentials, Resource, native session and complete application run as-is.
    code = snippets[0].replace(
        "https://api.futureagi.com/tracer/v1/traces",
        server.origin + "/tracer/v1/traces",
    )
    scope = {"__name__": __name__}
    exec(compile(code, "crewai_example.py", "exec"), scope)
    assert "Useful answer" in scope["result"].raw
    assert (
        len(
            [s for s in server.spans if attrs(s).get("gen_ai.operation.name") == "chat"]
        )
        == 1
    )
    exec(compile(snippets[1], "crewai_flow_example.py", "exec"), scope)
    with session(server):
        result = scope["ExplanationFlow"]().kickoff()
    assert result == {
        "summary": "Distributed tracing connects the steps in an agent workflow."
    }
    assert_transport(server)
