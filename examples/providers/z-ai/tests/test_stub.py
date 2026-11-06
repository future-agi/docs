"""The stand-in only claims what Z.ai documents, and answers the documented error cases."""
import json
import urllib.error
import urllib.request

import pytest
from conftest import MODEL, ZAI_KEY


def post(stub, body, key=ZAI_KEY, path="chat/completions"):
    request = urllib.request.Request(stub.url + path, data=json.dumps(body).encode(), method="POST")
    request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(request) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


MESSAGES = [{"role": "user", "content": "hi there"}]


def test_a_chat_response_has_the_documented_fields_and_no_object_field_by_default(plain_stub):
    status, raw = post(plain_stub, {"model": MODEL, "messages": MESSAGES})
    body = json.loads(raw)
    assert status == 200
    assert set(body) == {"id", "request_id", "created", "model", "choices", "usage"}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert set(body["usage"]) == {"prompt_tokens", "completion_tokens", "prompt_tokens_details", "total_tokens"}
    assert body["usage"]["total_tokens"] == body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]


def test_the_stream_ends_with_finish_reason_and_usage_then_done(plain_stub):
    status, raw = post(plain_stub, {"model": MODEL, "messages": MESSAGES, "stream": True})
    assert status == 200
    events = [line[len("data: "):] for line in raw.split("\n\n") if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert all("usage" not in c for c in chunks[:-1])
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1]["usage"]["total_tokens"] > 0
    assert all("object" not in c for c in chunks)
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == "Z.ai stand-in reply to: hi there"


def test_thinking_adds_reasoning_content_only_when_enabled(plain_stub):
    on = json.loads(post(plain_stub, {"model": MODEL, "messages": MESSAGES, "thinking": {"type": "enabled"}})[1])
    off = json.loads(post(plain_stub, {"model": MODEL, "messages": MESSAGES, "thinking": {"type": "disabled"}})[1])
    assert "reasoning_content" in on["choices"][0]["message"]
    assert "reasoning_content" not in off["choices"][0]["message"]


@pytest.mark.parametrize(
    "key, body, status, code",
    [
        (None, {"model": MODEL, "messages": MESSAGES}, 401, "1001"),
        ("wrong", {"model": MODEL, "messages": MESSAGES}, 401, "1000"),
        (ZAI_KEY, {"model": "not-a-glm", "messages": MESSAGES}, 400, "1211"),
        (ZAI_KEY, {"model": MODEL, "messages": MESSAGES, "tools": [{"type": "function", "function": {"name": "f"}}], "tool_choice": "required"}, 400, "1214"),
    ],
)
def test_documented_errors_use_the_documented_shape(plain_stub, key, body, status, code):
    got_status, raw = post(plain_stub, body, key=key)
    assert got_status == status
    assert json.loads(raw) == {"error": {"code": code, "message": json.loads(raw)["error"]["message"]}}


def test_only_the_documented_path_exists(plain_stub):
    status, _ = post(plain_stub, {"model": MODEL, "messages": MESSAGES}, path="completions")
    assert status == 404
