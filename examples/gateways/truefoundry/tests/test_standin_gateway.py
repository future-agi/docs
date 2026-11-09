"""The stand-in gateway: documented surface only, forwards to an OpenAI-compatible upstream."""
import importlib
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class Upstream(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Upstream.seen.append((self.path, self.headers.get("Authorization"), body))
        out = json.dumps({"model": body["model"], "choices": [{"message": {"role": "assistant", "content": "ok"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture()
def gateway(monkeypatch):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setenv("STANDIN_UPSTREAM_BASE_URL", f"http://127.0.0.1:{upstream.server_port}/v1")
    monkeypatch.setenv("STANDIN_UPSTREAM_API_KEY", "upstream-key")
    monkeypatch.setenv("STANDIN_TOKEN", "t")
    monkeypatch.setenv("STANDIN_MODELS", "openai-main/gpt-6-luna")
    import standin_gateway

    importlib.reload(standin_gateway)
    server = ThreadingHTTPServer(("127.0.0.1", 0), standin_gateway.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Upstream.seen.clear()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    upstream.shutdown()


def call(base, path="/chat/completions", token="t", model="openai-main/gpt-6-luna"):
    req = urllib.request.Request(
        base + path,
        data=json.dumps({"model": model, "messages": []}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_forwards_with_account_prefix_removed_and_upstream_key(gateway):
    status, body = call(gateway)
    assert status == 200 and body["model"] == "gpt-6-luna"
    assert Upstream.seen == [("/v1/chat/completions", "Bearer upstream-key", {"model": "gpt-6-luna", "messages": []})]


def test_serves_chat_completions_at_the_root_only(gateway):
    assert call(gateway, path="/v1/chat/completions")[0] == 404


def test_wrong_token_is_401_and_nothing_is_forwarded(gateway):
    assert call(gateway, token="nope")[0] == 401
    assert Upstream.seen == []


def test_unknown_and_forbidden_models_get_the_same_403(gateway):
    a = call(gateway, model="openai-main/does-not-exist")
    b = call(gateway, model="other-account/gpt-6-luna")
    # Real shape (2026-10-20): the message names the model, the type is AuthorizationError either way.
    assert a[0] == b[0] == 403
    assert a[1].keys() == b[1].keys() if isinstance(a[1], dict) else True
    assert "AuthorizationError" in str(a[1]) and "AuthorizationError" in str(b[1])
    assert Upstream.seen == []
