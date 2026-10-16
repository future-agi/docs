"""The stand-in only claims the parts of the ModelArk Chat API that BytePlus documents."""
import json
import urllib.error
import urllib.request

from conftest import ARK_KEY, MODEL


def _post(stub, payload, key=ARK_KEY, path="/chat/completions", root=None):
    req = urllib.request.Request((root or stub.url) + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_chat_completion_has_the_documented_fields(stub):
    status, body = _post(stub, {"model": MODEL, "messages": [{"role": "user", "content": "hi there"}]})
    data = json.loads(body)
    assert status == 200
    assert data["object"] == "chat.completion" and data["model"] == MODEL and data["service_tier"] == "default"
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "echo: hi there"}
    assert data["choices"][0]["finish_reason"] == "stop" and data["choices"][0]["logprobs"] is None
    usage = data["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage["prompt_tokens_details"] == {"cached_tokens": 0}
    assert usage["completion_tokens_details"] == {"reasoning_tokens": 0}


def test_the_documented_path_is_the_only_path(stub):
    assert _post(stub, {"model": MODEL, "messages": []}, path="/chat/completions")[0] == 200
    # the Coding Plan prefix is a different product and the stand-in does not serve it
    status, _ = _post(stub, {"model": MODEL, "messages": []}, path="/api/coding/v3/chat/completions", root=stub.root)
    assert status == 404


def test_thinking_adds_reasoning_content_and_tokens_only_when_not_disabled(stub):
    base = {"model": MODEL, "messages": [{"role": "user", "content": "q"}]}
    off = json.loads(_post(stub, {**base, "thinking": {"type": "disabled"}})[1])
    on = json.loads(_post(stub, {**base, "thinking": {"type": "enabled"}})[1])
    assert "reasoning_content" not in off["choices"][0]["message"]
    assert on["choices"][0]["message"]["reasoning_content"]
    assert off["usage"]["completion_tokens_details"]["reasoning_tokens"] == 0
    assert on["usage"]["completion_tokens_details"]["reasoning_tokens"] > 0


def test_errors_use_the_documented_code_type_and_message(stub):
    status, body = _post(stub, {"messages": []})
    assert status == 400
    assert json.loads(body)["error"]["code"] == "MissingParameter"
    for key in ("wrong", None):
        status, body = _post(stub, {"model": MODEL, "messages": []}, key=key)
        err = json.loads(body)["error"]
        assert (status, err["code"], err["type"]) == (401, "AuthenticationError", "Unauthorized")
        assert err["message"].startswith("The API key or AK/SK in the request is missing or invalid.")
        assert "Request id:" in err["message"]
    status, body = _post(stub, {"model": "does-not-exist-1", "messages": []})
    assert (status, json.loads(body)["error"]["code"]) == (404, "InvalidEndpointOrModel.NotFound")


def test_streaming_ends_with_done_and_usage_chunk_is_opt_in(stub):
    base = {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "one two"}]}
    _, plain = _post(stub, base)
    assert plain.rstrip().endswith("data: [DONE]")
    chunks = [json.loads(line[6:]) for line in plain.splitlines() if line.startswith("data: {")]
    assert all(c["usage"] is None for c in chunks)  # documented: usage is null unless asked for
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    _, with_usage = _post(stub, {**base, "stream_options": {"include_usage": True}})
    last = [json.loads(line[6:]) for line in with_usage.splitlines() if line.startswith("data: {")][-1]
    assert last["choices"] == [] and last["usage"]["total_tokens"] > 0


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
