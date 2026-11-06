#!/usr/bin/env python3
"""A refusing HTTP proxy that records where a client tries to connect.

Point a process at it with HTTPS_PROXY=http://127.0.0.1:<port>. An HTTPS client
that is configured with the real Z.ai base URL asks the proxy for
`CONNECT api.z.ai:443`. This server writes that target down and answers 403, so
no tunnel is opened and nothing leaves the machine.

It proves one thing: which host and port the unmodified recipe client dials.
It does not speak to Z.ai and it does not forward anything.
"""
import socketserver
import threading


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(65536).decode("latin-1").strip()
        while True:  # drain the header block
            header = self.rfile.readline(65536)
            if header in (b"\r\n", b"\n", b""):
                break
        method, _, rest = line.partition(" ")
        target = rest.rsplit(" ", 1)[0]
        self.server.seen.append({"method": method, "target": target})
        body = b"refused by connect_probe (no tunnel is opened)\n"
        self.wfile.write(
            b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )


class ConnectProbe(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host="127.0.0.1", port=0):
        super().__init__((host, port), _Handler)
        self.seen = []

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self


if __name__ == "__main__":
    probe = ConnectProbe(port=0).start()
    print(probe.url, flush=True)
    threading.Event().wait()
