"""The stand-in only claims the parts of the CometAPI chat endpoint that CometAPI documents."""
import json
import urllib.error
import urllib.request

from conftest import COMET_KEY, MODEL


def _post(stub, payload, key=COMET_KEY, path="/chat/completions", root=None):
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
    assert data["object"] == "chat.completion" and data["model"] == MODEL
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "echo: hi there"}
    assert data["choices"][0]["finish_reason"] == "stop" and data["choices"][0]["logprobs"] is None
    usage = data["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert set(usage["prompt_tokens_details"]) == {"audio_tokens", "cache_write_tokens", "cached_tokens"}
    assert set(usage["completion_tokens_details"]) == {
        "accepted_prediction_tokens",
        "audio_tokens",
        "reasoning_tokens",
        "rejected_prediction_tokens",
    }


def test_the_documented_error_envelope(stub):
    status, body = _post(stub, {"model": MODEL, "messages": []}, key="wrong")
    err = json.loads(body)["error"]
    assert status == 401
    assert err["type"] == "comet_api_error" and err["code"] == ""
    assert err["message"].startswith("invalid token (request id: ")
    status, body = _post(stub, {"messages": []})
    assert status == 400 and json.loads(body)["error"]["message"].startswith("model name is required (request id: ")


def test_the_documented_path_is_the_only_path(stub):
    assert _post(stub, {"model": MODEL, "messages": []}, path="/chat/completions")[0] == 200
    # a base URL without /v1 reaches /chat/completions, which the stand-in does not serve
    status, body = _post(stub, {"model": MODEL, "messages": []}, path="/chat/completions", root=stub.root)
    assert status == 404 and json.loads(body)["error"]["type"] == "comet_api_error"


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
