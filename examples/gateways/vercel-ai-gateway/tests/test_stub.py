"""The stand-in copies the status codes, error bodies, routes and stream usage of the live
gateway (2026-10-18). Its reply text is made up."""
import json
import urllib.error
import urllib.request

from conftest import GATEWAY_KEY, MODEL


def _post(stub, payload, key=GATEWAY_KEY, path="/chat/completions", base=None):
    req = urllib.request.Request((base or stub.url) + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def _error(body):
    return json.loads(body)["error"]


def test_chat_completion_shape(stub):
    status, body = _post(stub, {"model": MODEL, "messages": [{"role": "user", "content": "hi there"}]})
    data = json.loads(body)
    assert status == 200
    assert data["object"] == "chat.completion" and data["model"] == MODEL
    message = data["choices"][0]["message"]
    assert (message["role"], message["content"]) == ("assistant", "echo: hi there")
    assert message["provider_metadata"]["gateway"]["routing"]["originalModelId"] == MODEL
    assert data["generationId"] == data["id"] and data["id"].startswith("gen_")
    usage = data["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_errors_copy_the_live_bodies(stub):
    status, body = _post(stub, {"messages": []})
    assert status == 400
    assert _error(body) == {
        "message": "Invalid input: expected string, received undefined",
        "type": "invalid_request_error",
        "param": "model",
        "code": "invalid_request_error",
    }
    status, body = _post(stub, {"model": MODEL, "messages": []}, key="wrong")
    assert status == 401 and _error(body)["type"] == "authentication_error"
    assert _error(body)["message"].startswith("Authentication failed. Create an API key and set in AI_GATEWAY_API_KEY")
    status, body = _post(stub, {"model": MODEL, "messages": []}, key=None)
    assert (status, _error(body)) == (401, {"message": "Missing Authorization header", "type": "authentication_error"})
    status, body = _post(stub, {"model": "does-not-exist/x", "messages": []})
    assert (status, _error(body)) == (
        404,
        {"message": "Model 'does-not-exist/x' not found", "type": "model_not_found", "param": {"modelId": "does-not-exist/x"}},
    )


def test_wrong_base_url_paths(stub):
    # doubled /v1: JSON not_found_error
    status, body = _post(stub, {"model": MODEL, "messages": []}, path="/v1/chat/completions")
    assert status == 404 and _error(body)["code"] == "not_found_error"
    assert _error(body)["message"] == "The requested resource was not found: /v1/v1/chat/completions"
    # no /v1 at all: an HTML 404 page, not JSON
    status, body = _post(stub, {"model": MODEL, "messages": []}, base=stub.url[: -len("/v1")])
    assert status == 404 and body.lstrip().startswith("<!DOCTYPE html>")


def test_streaming_ends_with_done_and_always_reports_usage(stub):
    base = {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "one two"}]}
    for payload in (base, {**base, "stream_options": {"include_usage": True}}):
        _, text = _post(stub, payload)
        assert text.rstrip().endswith("data: [DONE]")
        chunks = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: {")]
        finish = chunks[-1]
        # like the live gateway: usage rides on the finish chunk, which still has a choice
        assert finish["choices"][0]["finish_reason"] == "stop" and finish["usage"]["total_tokens"] > 0
        assert [c for c in chunks if "usage" in c] == [finish]


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
