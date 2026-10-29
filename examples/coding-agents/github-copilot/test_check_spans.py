"""Contract tests for check_spans.py against a sanitized Copilot CLI 1.0.98 capture."""
from __future__ import annotations

import copy
import json
import pathlib
import unittest

import check_spans

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "copilot-cli-1.0.98-default.jsonl"


class CopilotSpanContract(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = FIXTURE.read_text(encoding="utf-8")
        self.spans = check_spans.load_spans(str(FIXTURE))

    def test_default_capture_passes(self) -> None:
        self.assertEqual(check_spans.check(self.spans, marker="MARKER_TH8230", raw=self.raw), [])

    def test_one_trace_rooted_at_invoke_agent(self) -> None:
        self.assertEqual(len({s["traceId"] for s in self.spans}), 1)
        root = [s for s in self.spans if not s.get("parentSpanId")]
        self.assertEqual([r["attributes"]["gen_ai.operation.name"] for r in root], ["invoke_agent"])
        children = [s for s in self.spans if s.get("parentSpanId") == root[0]["spanId"]]
        self.assertEqual({c["attributes"]["gen_ai.operation.name"] for c in children}, {"chat", "execute_tool"})

    def test_tokens_and_model_on_chat_spans(self) -> None:
        chats = [s for s in self.spans if s["attributes"]["gen_ai.operation.name"] == "chat"]
        self.assertTrue(chats)
        for c in chats:
            self.assertTrue(c["attributes"]["gen_ai.request.model"])
            self.assertGreater(c["attributes"]["gen_ai.usage.input_tokens"], 0)

    def test_content_attribute_fails_default_check(self) -> None:
        spans = copy.deepcopy(self.spans)
        spans[0]["attributes"]["gen_ai.tool.call.arguments"] = json.dumps({"path": "README.md"})
        errors = check_spans.check(spans, raw=self.raw)
        self.assertTrue(any("content attributes present" in e for e in errors))

    def test_marker_in_default_export_fails(self) -> None:
        errors = check_spans.check(self.spans, marker="secret-prompt", raw=self.raw + "secret-prompt")
        self.assertTrue(any("marker" in e for e in errors))

    def test_content_mode_requires_content(self) -> None:
        errors = check_spans.check(self.spans, content=True, raw=self.raw)
        self.assertTrue(any("no content attribute" in e for e in errors))

    def test_missing_conversation_id_fails(self) -> None:
        spans = copy.deepcopy(self.spans)
        del spans[0]["attributes"]["gen_ai.conversation.id"]
        self.assertTrue(any("conversation.id" in e for e in check_spans.check(spans, raw=self.raw)))

    def test_vscode_direct_span_shape_and_nested_parent(self) -> None:
        root = {"traceId": "t", "spanId": "r", "name": "invoke_agent",
                "attributes": {"gen_ai.operation.name": "invoke_agent", "gen_ai.conversation.id": "c"}}
        child = {"traceId": "t", "spanId": "c1", "parentSpanContext": {"spanId": "r"},
                 "name": "chat", "attributes": {"gen_ai.operation.name": "chat", "gen_ai.conversation.id": "c"}}
        tool = {"traceId": "t", "spanId": "c2", "parentSpanContext": {"spanId": "r"},
                "name": "execute_tool read", "attributes": {"gen_ai.operation.name": "execute_tool", "gen_ai.conversation.id": "c", "gen_ai.tool.name": "read"}}
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as fh:
            for record in (root, child, tool):
                fh.write(json.dumps(record) + "\n")
            fh.flush()
            spans = check_spans.load_spans(fh.name)
        self.assertEqual(check_spans.check(spans), [])

    def test_standalone_custom_notification_is_ignored(self) -> None:
        spans = copy.deepcopy(self.spans)
        spans.append({"traceId": "other", "spanId": "n", "name": "custom_notification", "attributes": {}})
        self.assertEqual(check_spans.check(spans, raw=self.raw), [])


if __name__ == "__main__":
    unittest.main()
