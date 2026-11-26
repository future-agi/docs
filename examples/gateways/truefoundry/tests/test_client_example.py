"""Exercise the README entry point, including agent/tool hierarchy and export."""
import json

import pytest
from traceai_openai import OpenAIInstrumentor

import client_example
from test_client_tracing import MODEL, _gateway, httpx
from test_page_snippet import PRIVACY_FLAGS, attributes, decode_request, receiver


@pytest.mark.parametrize("mode", ["agent", "stream", "error"])
def test_readme_example(monkeypatch, capsys, receiver, mode):
    endpoint, received = receiver
    for flag in PRIVACY_FLAGS:
        monkeypatch.setenv(flag, "true")
    for key, value in {
        "FI_BASE_URL": endpoint, "FI_API_KEY": "synthetic-key", "FI_SECRET_KEY": "synthetic-secret",
        "TFY_BASE_URL": "https://gateway.truefoundry.ai", "TFY_API_KEY": "tfy-test-token",
        "TFY_MODEL": "openai-main/forbidden" if mode == "error" else MODEL,
        "FI_PROJECT_NAME": "truefoundry-gateway",
    }.items():
        monkeypatch.setenv(key, value)

    def gateway(request):
        body = json.loads(request.content)
        if mode != "agent":
            return _gateway(request)
        messages = body["messages"]
        if messages[-1]["role"] == "tool":
            assert json.loads(messages[-1]["content"])["status"] == "shipped"
            message = {"role": "assistant", "content": "Order shipped"}
            finish = "stop"
        else:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "tool-1", "type": "function", "function": {
                    "name": "get_order_status", "arguments": '{"order_id":"A-1042"}',
                },
            }]}
            finish = "tool_calls"
        return httpx.Response(200, json={
            "id": "c1", "object": "chat.completion", "created": 1, "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        })

    class MockedOpenAI(client_example.OpenAI):
        def __init__(self, **kwargs):
            super().__init__(http_client=httpx.Client(transport=httpx.MockTransport(gateway)), **kwargs)

    monkeypatch.setattr(client_example, "OpenAI", MockedOpenAI)
    try:
        code = client_example.main(["client_example.py"] + (["--stream"] if mode == "stream" else []))
    finally:
        OpenAIInstrumentor().uninstrument()
    assert code == (1 if mode == "error" else 0)
    output = capsys.readouterr()
    if mode == "agent":
        assert output.out.strip() == "Order shipped"
    assert received
    spans = [span for record in received for resource in decode_request(record)[3].resource_spans
             for scope in resource.scope_spans for span in scope.spans]
    if mode == "agent":
        assert len(spans) == 4
        kinds = [attributes(s.attributes)["gen_ai.span.kind"] for s in spans]
        assert sorted(kinds) == ["AGENT", "LLM", "LLM", "TOOL"]
        root = next(s for s in spans if attributes(s.attributes)["gen_ai.span.kind"] == "AGENT")
        assert not root.parent_span_id
        assert all(s.trace_id == root.trace_id for s in spans)
        assert all(s.parent_span_id == root.span_id for s in spans if s is not root)
    elif mode == "stream":
        assert len(spans) == 1
        assert attributes(spans[0].attributes)["gen_ai.request.model"] == MODEL
    else:
        assert any(s.status.code == 2 for s in spans)
    for record in received:
        body = decode_request(record)[2]
        for marker in (b"A-1042", b"dev@example.test", b"exception.stacktrace", b"synthetic-secret", b"tfy-test-token"):
            assert marker not in body
