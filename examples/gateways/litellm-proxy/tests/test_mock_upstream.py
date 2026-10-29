"""The mock upstream behaves like an OpenAI-compatible chat API, including errors, tools and streams."""
from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from tests.helpers import serve_in_thread

import mock_upstream


class MockUpstreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.state = mock_upstream.serve("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"
        serve_in_thread(cls.server)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, body):
        req = urllib.request.Request(
            self.base + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            try:
                return err.code, err.read()
            finally:
                err.close()

    def test_plain_reply_echoes_marker_and_reports_usage(self):
        status, raw = self.post({"model": "m", "messages": [{"role": "user", "content": "hi MARK_abc123"}]})
        body = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertIn("MARK_abc123", body["choices"][0]["message"]["content"])
        self.assertGreater(body["usage"]["prompt_tokens"], 0)
        self.assertEqual(body["usage"]["total_tokens"], body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"])

    def test_tool_call_then_final_answer(self):
        tool = {"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object"}}}
        first = json.loads(self.post({"messages": [{"role": "user", "content": "MARK_t1"}], "tools": [tool]})[1])
        call = first["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "get_weather")
        self.assertEqual(json.loads(call["function"]["arguments"]), {"query": "MARK_t1"})
        self.assertEqual(first["choices"][0]["finish_reason"], "tool_calls")
        messages = [
            {"role": "user", "content": "MARK_t1"},
            {"role": "assistant", "content": None, "tool_calls": [call]},
            {"role": "tool", "tool_call_id": call["id"], "content": "sunny"},
        ]
        second = json.loads(self.post({"messages": messages, "tools": [tool]})[1])
        self.assertEqual(second["choices"][0]["finish_reason"], "stop")
        self.assertIn("MARK_t1", second["choices"][0]["message"]["content"])

    def test_fail_upstream_returns_500_with_fixed_marker(self):
        status, raw = self.post({"messages": [{"role": "user", "content": "FAIL_UPSTREAM"}]})
        self.assertEqual(status, 500)
        self.assertIn(mock_upstream.ERROR_MARKER, raw.decode())

    def test_stream_sends_usage_only_when_requested(self):
        def chunks(extra):
            req = urllib.request.Request(
                self.base + "/chat/completions",
                data=json.dumps({"messages": [{"role": "user", "content": "MARK_s1"}], "stream": True, **extra}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                lines = [l.decode().strip() for l in resp.read().splitlines() if l.startswith(b"data: ")]
            return [json.loads(l[6:]) for l in lines if l != "data: [DONE]"], lines[-1]

        with_usage, last = chunks({"stream_options": {"include_usage": True}})
        self.assertEqual(last, "data: [DONE]")
        self.assertIn("usage", with_usage[-1])
        without, _ = chunks({})
        self.assertTrue(all("usage" not in c for c in without))
        text = "".join(c["choices"][0]["delta"].get("content", "") for c in with_usage if c["choices"])
        self.assertIn("MARK_s1", text)

    def test_counts_requests(self):
        before = self.state.requests
        self.post({"messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(self.state.requests, before + 1)


if __name__ == "__main__":
    unittest.main()
