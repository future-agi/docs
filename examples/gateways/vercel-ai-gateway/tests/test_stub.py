"""The stand-in only claims the parts of the Chat Completions API that Vercel documents."""
import json
import urllib.error
import urllib.request

from conftest import GATEWAY_KEY, MODEL


def _post(stub, payload, key=GATEWAY_KEY, path="/chat/completions"):
    req = urllib.request.Request(stub.url + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_chat_completion_shape(stub):
    status, body = _post(stub, {"model": MODEL, "messages": [{"role": "user", "content": "hi there"}]})
    data = json.loads(body)
    assert status == 200
    assert data["object"] == "chat.completion" and data["model"] == MODEL
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "echo: hi there"}
    usage = data["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_errors_use_the_documented_body(stub):
    status, body = _post(stub, {"messages": []})
    assert status == 400
    assert json.loads(body)["error"] == {
        "message": "Invalid request: missing required parameter 'model'",
        "type": "invalid_request_error",
        "param": "model",
        "code": "missing_parameter",
    }
    assert _post(stub, {"model": MODEL, "messages": []}, key="wrong")[0] == 401
    assert _post(stub, {"model": MODEL, "messages": []}, key=None)[0] == 401
    assert _post(stub, {"model": "does-not-exist/x", "messages": []})[0] == 404


def test_streaming_ends_with_done_and_usage_is_opt_in(stub):
    base = {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "one two"}]}
    _, plain = _post(stub, base)
    assert plain.rstrip().endswith("data: [DONE]")
    assert '"usage"' not in plain
    _, with_usage = _post(stub, {**base, "stream_options": {"include_usage": True}})
    assert '"usage"' in with_usage


def test_tool_call_then_final_answer(stub):
    tools = [{"type": "function", "function": {"name": "lookup_record", "parameters": {"type": "object"}}}]
    _, first = _post(stub, {"model": MODEL, "tools": tools, "messages": [{"role": "user", "content": "find x"}]})
    call = json.loads(first)["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "lookup_record"
    assert json.loads(call["function"]["arguments"]) == {"query": "find x"}
    _, second = _post(
        stub,
        {"model": MODEL, "tools": tools, "messages": [{"role": "tool", "tool_call_id": call["id"], "content": "done"}]},
    )
    assert json.loads(second)["choices"][0]["finish_reason"] == "stop"
