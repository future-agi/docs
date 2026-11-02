"""The normal application must not print a partial answer as success."""

import json
from unittest.mock import Mock

import pytest

import client_example
from test_client_tracing import MODEL, httpx


@pytest.mark.parametrize(
    "ending", ["eof", "done", "usage", "empty", "stop", "length", "content_filter"]
)
def test_stream_main_requires_complete_answer(monkeypatch, capsys, ending):
    chunk = {
        "id": "synthetic-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": MODEL,
        "choices": [
            {"index": 0, "delta": {"content": "answer text"}, "finish_reason": None}
        ],
    }
    payload = "" if ending == "empty" else "data: " + json.dumps(chunk) + "\n\n"
    if ending in {"stop", "length", "content_filter"}:
        chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": ending}]
        payload += "data: " + json.dumps(chunk) + "\n\n"
    if ending in {"usage", "stop"}:
        chunk["choices"] = []
        chunk["usage"] = {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4}
        payload += "data: " + json.dumps(chunk) + "\n\n"
    if ending in {"done", "stop"}:
        payload += "data: [DONE]\n\n"
    responses = []

    def handler(request):
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=httpx.ByteStream(payload.encode()),
        )
        responses.append(response)
        return response

    provider = Mock()
    with client_example.OpenAI(
        api_key="synthetic",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        monkeypatch.setattr(client_example, "build", lambda: (provider, client, None))
        code = client_example.main(["client_example.py", "--stream", "question"])
    output = capsys.readouterr()
    assert code == (0 if ending == "stop" else 1)
    assert output.out.strip() == ("answer text" if ending == "stop" else "")
    assert bool(output.err) == (ending != "stop")
    assert responses[0].is_closed
    provider.force_flush.assert_called_once_with()
    provider.shutdown.assert_called_once_with()


@pytest.mark.parametrize(
    "error", [RuntimeError("synthetic failure"), KeyboardInterrupt()]
)
def test_stream_cleanup_preserves_iteration_error(error):
    class InterruptedStream:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def __iter__(self):
            raise error

    stream = InterruptedStream()
    client = Mock()
    client.chat.completions.create.return_value = stream
    with pytest.raises(type(error)) as caught:
        client_example.run_stream(client, MODEL, "question")
    assert caught.value is error
    assert stream.closed
