"""send_requests.py drives each scenario; here the mock upstream plays the part of the proxy."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from tests.helpers import serve_in_thread

import mock_upstream
import send_requests


class ScenarioDriverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.state = mock_upstream.serve("127.0.0.1", 0)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        serve_in_thread(cls.server)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_driver(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = send_requests.main_with_args(["--proxy", self.url, "--key", "sk-test", "--marker", "MARK_drv", *argv])
        return code, [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]

    def test_default_scenarios_report_status_per_line(self):
        code, lines = self.run_driver("--only", "plain,stream,tools,error,joined")
        self.assertEqual(code, 0)
        by_name = {l["scenario"]: l for l in lines}
        self.assertEqual(by_name["plain"]["status"], 200)
        self.assertEqual(by_name["stream"]["status"], 200)
        self.assertEqual(by_name["tools.call"]["status"], 200)
        self.assertEqual(by_name["tools.result"]["status"], 200)
        self.assertEqual(by_name["error"]["status"], 500)

    def test_joined_prints_the_trace_context_it_sent(self):
        _, lines = self.run_driver("--only", "joined")
        joined = lines[0]
        self.assertEqual(len(joined["trace_id"]), 32)
        self.assertEqual(len(joined["parent_span_id"]), 16)

    def test_unknown_scenario_is_refused(self):
        code, lines = self.run_driver("--only", "nonsense")
        self.assertEqual(code, 2)
        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
