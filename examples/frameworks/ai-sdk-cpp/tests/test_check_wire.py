"""check_wire.py against the recorded probe output (a real run of the pinned SDK on 2026-10-16), plus mutations."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "wire_probe"))
import check_wire  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "probe_out")


def fresh_copy():
    d = tempfile.mkdtemp()
    for name in os.listdir(FIXTURE):
        shutil.copy(os.path.join(FIXTURE, name), d)
    return d


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def failed(results):
    return [name for name, ok, _ in results if not ok]


class CheckWireTest(unittest.TestCase):
    def test_recorded_run_satisfies_every_expectation(self):
        results = check_wire.check(FIXTURE)
        self.assertGreaterEqual(len(results), 19)
        self.assertEqual(failed(results), [])

    def test_otlp_shaped_body_is_caught(self):
        d = fresh_copy()
        path = os.path.join(d, "run.jsonl")
        rec = json.loads(read(path).splitlines()[0])
        rec["body"] = {"resourceSpans": []}
        rec["path"] = "/v1/traces"
        write(path, json.dumps(rec) + "\n")
        bad = failed(check_wire.check(d))
        self.assertIn("run: path is /api/public/ingestion", bad)
        self.assertIn("run: body is JSON with a single 'batch' key (not OTLP)", bad)

    def test_future_agi_style_headers_are_caught(self):
        d = fresh_copy()
        path = os.path.join(d, "run.jsonl")
        rec = json.loads(read(path).splitlines()[0])
        rec["headers"]["X-Api-Key"] = "x"
        write(path, json.dumps(rec) + "\n")
        self.assertIn("run: no X-Api-Key / X-Secret-Key header", failed(check_wire.check(d)))

    def test_second_post_after_second_end_is_caught(self):
        d = fresh_copy()
        path = os.path.join(d, "run.jsonl")
        line = read(path).splitlines()[0] + "\n"
        write(path, line + line)
        self.assertIn("run: exactly one POST although end() was called twice", failed(check_wire.check(d)))

    def test_a_flush_without_end_is_caught(self):
        d = fresh_copy()
        shutil.copy(os.path.join(FIXTURE, "run.jsonl"), os.path.join(d, "noend.jsonl"))
        self.assertIn("noend: no POST at all", failed(check_wire.check(d)))

    def test_retry_after_failed_strict_flush_is_caught(self):
        d = fresh_copy()
        path = os.path.join(d, "strict-down.stdout.txt")
        text = read(path).replace("end#1=0 end#2=1", "end#1=0 end#2=0")
        write(path, text)
        self.assertIn("strict-down: first end() false, second end() true (no retry)", failed(check_wire.check(d)))


if __name__ == "__main__":
    unittest.main()
