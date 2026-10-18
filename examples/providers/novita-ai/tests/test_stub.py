"""The stand-in claims only the parts of the Novita chat route that Novita documents, and its
statuses, error bodies, routes and stream usage match the live API as observed on 2026-10-18."""
import json
import urllib.error
import urllib.request

from conftest import MODEL, NOVITA_KEY


def _post(stub, payload, key=NOVITA_KEY, path="/chat/completions", root=None):
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
    status, body = _post(stub, {"model": MODEL, "max_tokens": 16, "messages": [{"role": "user", "content": "hi there"}]})
    data = json.loads(body)
    assert status == 200
    assert data["object"] == "chat.completion" and data["model"] == MODEL
    assert {"id", "created", "choices", "usage"} <= set(data)
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "echo: hi there"}
    assert data["choices"][0]["finish_reason"] == "stop" and data["choices"][0]["index"] == 0
    usage = data["usage"]
    assert set(usage) == {"prompt_tokens", "completion_tokens", "total_tokens"}
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_the_error_envelope_and_status_codes_match_the_live_api(stub):
    status, body = _post(stub, {"model": MODEL, "messages": []}, key="wrong")
    assert status == 401
    assert json.loads(body) == {"code": 401, "reason": "FAILED_TO_AUTH", "message": "failed to authenticate API key", "metadata": {}}
    status, body = _post(stub, {"model": "novita-ai-example/no-such-model", "messages": []})
    assert status == 404
    assert json.loads(body) == {
        "code": 404,
        "reason": "MODEL_NOT_FOUND",
        "message": "model not found",
        "metadata": {"reason": "model: novita-ai-example/no-such-model not found"},
    }
    status, body = _post(stub, {"messages": []})
    assert status == 404 and json.loads(body)["metadata"] == {"reason": "model:  not found"}


def test_the_three_live_routes_are_served_and_nothing_else(stub):
    for root in ("/openai/v1", "/openai", "/v3/openai"):
        assert _post(stub, {"model": MODEL, "messages": []}, root=stub.root + root)[0] == 200
    for root in (stub.root, stub.root + "/v1", stub.root + "/openai/v1/v1"):
        assert _post(stub, {"model": MODEL, "messages": []}, root=root) == (404, "404 page not found")


def test_stream_usage_chunk_with_or_without_the_option(stub):
    base = {"model": MODEL, "messages": [{"role": "user", "content": "a b"}], "stream": True}
    for options in ({"include_usage": True}, None):
        payload = dict(base, **({"stream_options": options} if options else {}))
        _, body = _post(stub, payload)
        events = [e[len("data: "):] for e in body.split("\n\n") if e.startswith("data: ")]
        assert events[-1] == "[DONE]"
        chunks = [json.loads(e) for e in events[:-1]]
        (usage_chunk,) = [c for c in chunks if "usage" in c]
        assert usage_chunk["choices"] == [] and usage_chunk["usage"]["total_tokens"] > 0
