"""The stand-in only claims the parts of the Novita chat route that Novita documents."""
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


def test_the_error_envelope_and_status_codes(stub):
    status, body = _post(stub, {"model": MODEL, "messages": []}, key="wrong")
    err = json.loads(body)
    assert status == 401
    assert (err["code"], err["reason"]) == (401, "FAILED_TO_AUTH") and "trace_id" in err["metadata"]
    status, body = _post(stub, {"messages": []})
    assert status == 400 and json.loads(body)["reason"] == "INVALID_REQUEST_BODY"


def test_both_openai_client_paths_are_routed_and_nothing_else(stub):
    assert _post(stub, {"model": MODEL, "messages": []}, root=stub.root + "/openai/v1")[0] == 200
    assert _post(stub, {"model": MODEL, "messages": []}, root=stub.root + "/openai")[0] == 200
    for root in (stub.root + "/v3/openai", stub.root, stub.root + "/v1", stub.root + "/openai/v1/v1"):
        status, body = _post(stub, {"model": MODEL, "messages": []}, root=root)
        assert status == 404 and json.loads(body)["reason"] == "PATH_NOT_FOUND"


def test_stream_usage_chunk_only_when_asked(stub):
    base = {"model": MODEL, "messages": [{"role": "user", "content": "a b"}], "stream": True}
    for options, expect_usage in (({"include_usage": True}, True), (None, False)):
        payload = dict(base, **({"stream_options": options} if options else {}))
        _, body = _post(stub, payload)
        events = [e[len("data: "):] for e in body.split("\n\n") if e.startswith("data: ")]
        assert events[-1] == "[DONE]"
        chunks = [json.loads(e) for e in events[:-1]]
        usage_chunks = [c for c in chunks if "usage" in c]
        assert bool(usage_chunks) == expect_usage
        if expect_usage:
            assert usage_chunks[0]["choices"] == [] and usage_chunks[0]["usage"]["total_tokens"] > 0
