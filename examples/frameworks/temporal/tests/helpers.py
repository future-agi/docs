"""Test doubles: an OpenAI-compatible model on localhost, and span recorders."""
import collections
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openai import AsyncOpenAI
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class RecordingExporter(SpanExporter):
    """Keeps what would have left the process, one entry per export."""

    def __init__(self) -> None:
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class StartCounter(SpanProcessor):
    """Counts every span that was started, including the ones a replay creates and never exports."""

    def __init__(self) -> None:
        self.started = collections.Counter()

    def on_start(self, span, parent_context=None):
        self.started[span.name] += 1


class MockModel:
    """A local OpenAI-compatible chat-completions endpoint, so the real openai SDK makes a real HTTP call.

    With tools in the request it answers with a get_weather tool call; otherwise with one sentence.
    A request for `fail_for_model` is answered with a 404 whose message is `error_text`.
    """

    def __init__(self, marker: str = "", fail_for_model: str | None = None, error_text: str = "") -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                outer.requests.append(body)
                status, payload = outer.answer(body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.marker = marker
        self.fail_for_model = fail_for_model
        self.error_text = error_text
        self.requests: list[dict] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def client(self) -> AsyncOpenAI:
        return AsyncOpenAI(api_key="sk-model-key-FIXTURE-77be", base_url=self.base_url, max_retries=0)

    def answer(self, body: dict) -> tuple[int, dict]:
        if self.fail_for_model and body["model"] == self.fail_for_model:
            error = {"message": self.error_text or "model not found", "type": "invalid_request_error", "code": "model_not_found"}
            return 404, {"error": error}
        if body.get("tools"):
            call = {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": json.dumps({"city": f"Lisbon{self.marker}"})}}
            message, finish = {"role": "assistant", "content": None, "tool_calls": [call]}, "tool_calls"
        else:
            message, finish = {"role": "assistant", "content": f"It is sunny in Lisbon{self.marker}."}, "stop"
        return 200, {
            "id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }

    def close(self) -> None:
        self._server.shutdown()


def dump(spans) -> str:
    """Everything a span carries, as one string: attributes, resource, status, events."""
    parts = []
    for s in spans:
        parts.append(json.dumps(
            {
                "name": s.name,
                "attributes": dict(s.attributes or {}),
                "resource": dict(s.resource.attributes),
                "status": [str(s.status.status_code), s.status.description],
                "events": [{"name": e.name, "attributes": dict(e.attributes or {})} for e in s.events],
            },
            default=str,
        ))
    return "\n".join(parts)
