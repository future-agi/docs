"""A loopback-only model fixture for the Ridgeline Spring AI tracing example."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class StockFixture(BaseHTTPRequestHandler):
    def read_body(self):
        if self.headers.get("Transfer-Encoding", "").lower() != "chunked":
            return self.rfile.read(int(self.headers["Content-Length"]))
        data = bytearray()
        while True:
            size = int(self.rfile.readline().split(b";", 1)[0].strip(), 16)
            if size == 0:
                return data
            data.extend(self.rfile.read(size))
            self.rfile.readline()

    def do_POST(self):
        body = json.loads(self.read_body())
        if self.path == "/v1/embeddings":
            reply = {
                "object": "list",
                "model": "ridgeline-embedding",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            }
        elif self.path == "/v1/chat/completions":
            if any(message["role"] == "tool" for message in body["messages"]):
                message = {"role": "assistant", "content": "I can't confirm stock right now."}
                reason = "stop"
            else:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "stock-1", "type": "function",
                        "function": {"name": "checkStock", "arguments": json.dumps({"sku": "tent-fly"})},
                    }],
                }
                reason = "tool_calls"
            reply = {
                "id": "stock-check", "created": 1, "object": "chat.completion",
                "model": "ridgeline-chat",
                "choices": [{"index": 0, "message": message, "finish_reason": reason}],
                "usage": {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9},
            }
        else:
            self.send_error(404)
            return
        payload = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 18798), StockFixture) as server:
        server.serve_forever()
