"""Contract tests on real LiteLLM Proxy 1.105.1 exports (captured from the official Docker image).

The fixtures in tests/fixtures are what the proxy really sent to an OTLP/HTTP endpoint, taken by
``run_e2e.sh`` with the mock upstream. These tests pin what the Future AGI recipe relies on.
"""
from __future__ import annotations

import json
import re
import unittest

from tests.helpers import FIXTURES, chat_spans, fixture

import otlp_contract as oc

KEY_SHAPE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")


def scenario(meta, name):
    return next(s for s in meta["scenarios"] if s["scenario"] == name)


class WireTest(unittest.TestCase):
    """What the exporter sends on the wire (from the sink's request log)."""

    def test_every_fixture_sends_only_uncompressed_traces_with_both_key_headers(self):
        for path in sorted(FIXTURES.glob("*.meta.json")):
            meta = json.loads(path.read_text())
            with self.subTest(fixture=path.name):
                self.assertTrue(meta["requests"])
                for r in meta["requests"]:
                    self.assertEqual(r["signal"], "traces")
                    self.assertEqual(r["path"], "/v1/traces")
                    self.assertEqual(r["content_encoding"], "")
                    self.assertEqual(r["content_type"], "application/x-protobuf")
                    self.assertEqual(sorted(r["auth_headers_present"]), ["x-api-key", "x-secret-key"])

    def test_fixtures_were_taken_from_the_tested_version(self):
        for path in sorted(FIXTURES.glob("*.meta.json")):
            self.assertEqual(json.loads(path.read_text())["litellm_version"], "1.105.1")


class ProjectRoutingTest(unittest.TestCase):
    """AC-02 / D-INGEST: project_name must be a resource attribute on every ResourceSpans."""

    def test_project_name_from_otel_resource_attributes_is_on_every_resource(self):
        for name in ("docker-v2-content-off", "docker-v2-content-on", "docker-v1-content-off", "docker-v2-scrubbed"):
            spans, _, docs = fixture(name)
            with self.subTest(fixture=name):
                ok, why = oc.collector_accepts(docs)
                self.assertTrue(ok, why)
                self.assertEqual({s.resource["project_name"] for s in spans}, {"litellm-proxy-e2e"})
                self.assertEqual({s.resource["project_type"] for s in spans}, {"observe"})

    def test_batch_without_project_name_is_one_the_collector_rejects(self):
        spans, meta, docs = fixture("docker-v2-no-project")
        ok, why = oc.collector_accepts(docs)
        self.assertFalse(ok)
        self.assertIn("no project_name", why)
        self.assertTrue(all("project_name" not in s.resource for s in spans))
        # LiteLLM itself still sets service.name, so a missing project is not a LiteLLM failure
        self.assertEqual({s.resource["service.name"] for s in spans}, {"litellm"})


class V2ShapeTest(unittest.TestCase):
    def setUp(self):
        self.spans, self.meta, _ = fixture("docker-v2-content-off")
        self.by_trace = oc.traces(self.spans)

    def test_one_request_is_server_span_auth_and_one_chat_span(self):
        ok_traces = [t for t in self.by_trace.values() if all(s.status != "ERROR" for s in t)]
        self.assertGreaterEqual(len(ok_traces), 5)
        for members in ok_traces:
            names = sorted(s.name.split(" ")[0] for s in members)
            self.assertEqual(names, ["POST", "auth", "chat"], members[0].trace_id)
            root = oc.roots(members)[0]
            self.assertEqual((root.name, root.kind), ("POST /v1/chat/completions", "SERVER"))

    def test_llm_call_span_carries_model_group_provider_and_tokens(self):
        for s in chat_spans(self.spans):
            if s.status == "ERROR":
                continue
            self.assertEqual(s.kind, "CLIENT")
            self.assertEqual(s.name, f"chat {s.attrs['gen_ai.request.model']}")
            self.assertEqual(s.attrs["gen_ai.request.model"], "demo-model")  # the model group the caller sent
            self.assertEqual(s.attrs["litellm.provider.model"], "openai/mock-model")  # what the proxy called
            self.assertEqual(s.attrs["gen_ai.provider.name"], "openai")
            self.assertGreater(s.attrs["gen_ai.usage.input_tokens"], 0)
            self.assertGreater(s.attrs["gen_ai.usage.output_tokens"], 0)
            self.assertEqual(
                s.attrs["gen_ai.usage.total_tokens"],
                s.attrs["gen_ai.usage.input_tokens"] + s.attrs["gen_ai.usage.output_tokens"],
            )

    def test_streaming_request_still_ends_with_usage(self):
        streamed = [s for s in chat_spans(self.spans) if s.attrs.get("litellm.request.streaming") is True]
        self.assertTrue(streamed)
        for s in streamed:
            self.assertGreater(s.attrs["gen_ai.usage.output_tokens"], 0)
            self.assertIn("gen_ai.response.time_to_first_chunk", s.attrs)

    def test_tool_definitions_are_exported_but_not_tool_arguments_or_results(self):
        with_tools = [s for s in chat_spans(self.spans) if s.attrs.get("litellm.request.tools.declared")]
        self.assertTrue(with_tools)
        self.assertEqual(with_tools[0].attrs["gen_ai.tool.0.name"], "get_weather")
        self.assertFalse(oc.contains(self.spans, "MARK_dkr2off"))
        self.assertFalse(oc.contains(self.spans, "sunny and 21C"))

    def test_upstream_failure_marks_the_llm_span_and_the_request_as_error(self):
        errors = [s for s in chat_spans(self.spans) if s.status == "ERROR"]
        self.assertEqual(len(errors), 2)  # the 500 from the upstream and the refused connection
        for s in errors:
            self.assertEqual(s.attrs["error.type"], "InternalServerError")
            self.assertEqual(s.attrs["gen_ai.operation.name"], "chat")
            roots = oc.roots(self.by_trace[s.trace_id])
            self.assertEqual(roots[0].status, "ERROR")

    def test_traceparent_joins_the_callers_trace(self):
        joined = scenario(self.meta, "joined")
        members = self.by_trace[joined["trace_id"]]
        root = oc.roots(members)[0]
        self.assertEqual(root.name, "POST /v1/chat/completions")
        self.assertEqual(root.parent_id, joined["parent_span_id"])

    def test_rejected_key_still_exports_a_trace_with_a_hash_not_the_key(self):
        bad = [s for s in self.spans if s.name.startswith("auth") and s.status == "ERROR"]
        self.assertEqual(len(bad), 1)
        hashes = {s.attrs["litellm.api_key.hash"] for s in self.spans if "litellm.api_key.hash" in s.attrs}
        self.assertIn("litellm_proxy_master_key", hashes)  # the master key shows as this literal, not its value
        digests = [h for h in hashes if h != "litellm_proxy_master_key"]
        self.assertTrue(digests)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in digests), digests)

    def test_health_probes_are_not_traced(self):
        self.assertFalse([s for s in self.spans if "health" in s.name.lower()])


class PrivacyTest(unittest.TestCase):
    """AC-04: with content capture off there is no prompt, response, tool argument or tool result."""

    def test_marker_and_headers_never_appear_with_content_off(self):
        for name, marker in (("docker-v2-content-off", "MARK_dkr2off"), ("docker-v1-content-off", "MARK_fxv1off"), ("docker-v2-scrubbed", "MARK_dkr2scrub")):
            spans, _, _ = fixture(name)
            with self.subTest(fixture=name):
                for needle in (marker, "weather for", "mock reply", "final answer", "COOKIE_", "CUSTOM_", "APIKEYHDR_", "203.0.113.7"):
                    self.assertFalse(oc.contains(spans, needle), needle)
                self.assertFalse(KEY_SHAPE.search(json.dumps([s.attrs for s in spans])), "something shaped like an API key was exported")
                self.assertFalse(oc.contains(spans, "uthorization"))

    def test_message_attributes_exist_only_when_content_is_on(self):
        off, _, _ = fixture("docker-v2-content-off")
        on, _, _ = fixture("docker-v2-content-on")
        self.assertFalse([s for s in off if "gen_ai.input.messages" in s.attrs or "gen_ai.output.messages" in s.attrs])
        for s in chat_spans(on):
            self.assertIn("gen_ai.input.messages", s.attrs)
        self.assertTrue(oc.contains(on, "MARK_fxv2on"))
        calls = [s for s in chat_spans(on) if "tool_calls\": [{" in s.attrs.get("gen_ai.output.messages", "")]
        self.assertTrue(calls)  # tool-call arguments appear only on the opt-in path
        self.assertIn("MARK_fxv2on", calls[0].attrs["gen_ai.output.messages"])

    def test_known_gaps_content_off_still_exports_error_text_stack_traces_and_addresses(self):
        """This is the limitation the page documents. If a LiteLLM release fixes it, this fixture does not change."""
        spans, _, _ = fixture("docker-v2-content-off")
        found = oc.leaks(spans)
        for key in ("error.message", "litellm.provider.error.stack_trace", "exception.stacktrace", "net.peer.ip", "http.user_agent", "server.address"):
            self.assertIn(key, found)
        self.assertTrue(oc.contains(spans, "UPSTREAM_ERROR_MARKER_7f3a"))  # raw provider error text

    def test_collector_scrub_config_removes_them_and_keeps_the_trace_useful(self):
        spans, _, docs = fixture("docker-v2-scrubbed")
        self.assertEqual(oc.leaks(spans), [])
        for needle in ("UPSTREAM_ERROR_MARKER_7f3a", "Traceback", "/app/.venv", "host.docker.internal", "172.17."):
            self.assertFalse(oc.contains(spans, needle), needle)
        ok, why = oc.collector_accepts(docs)
        self.assertTrue(ok, why)
        errors = [s for s in chat_spans(spans) if s.status == "ERROR"]
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(s.attrs.get("error.type") == "InternalServerError" for s in errors))
        self.assertTrue(all(s.attrs.get("gen_ai.usage.input_tokens") is not None for s in chat_spans(spans) if s.status != "ERROR"))


class V1ShapeTest(unittest.TestCase):
    def setUp(self):
        self.spans, self.meta, _ = fixture("docker-v1-content-off")
        self.by_trace = oc.traces(self.spans)

    def test_request_is_one_proxy_span_with_operational_children_and_an_llm_span(self):
        names = {s.name for s in self.spans}
        self.assertTrue({"Received Proxy Server Request", "litellm_request", "auth", "proxy_pre_call", "router", "self"} <= names)
        ok = next(t for t in self.by_trace.values() if all(s.status != "ERROR" for s in t))
        self.assertGreaterEqual(len(ok), 7)  # versus 3 on v2

    def test_llm_span_names_the_provider_model_and_has_no_gen_ai_operation(self):
        calls = [s for s in self.spans if s.name == "litellm_request" and s.status != "ERROR"]
        self.assertTrue(calls)
        for s in calls:
            self.assertEqual(s.attrs["gen_ai.request.model"], "mock-model")  # provider model, not the group
            self.assertEqual(s.attrs["litellm.model_group"], "demo-model")
            self.assertNotIn("gen_ai.operation.name", s.attrs)
            self.assertEqual(s.attrs["llm.request.type"], "acompletion")
            self.assertGreater(s.attrs["gen_ai.usage.input_tokens"], 0)

    def test_failure_adds_a_failed_proxy_server_request_span(self):
        failed = [s for s in self.spans if s.name == "Failed Proxy Server Request"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].status, "ERROR")

    def test_v1_exports_extra_request_metadata_even_with_content_off(self):
        found = oc.leaks(self.spans)
        for key in ("metadata.requester_ip_address", "metadata.user_agent", "metadata.requester_metadata", "hidden_params"):
            self.assertIn(key, found)

    def test_traceparent_joins_the_callers_trace(self):
        joined = scenario(self.meta, "joined")
        members = self.by_trace[joined["trace_id"]]
        self.assertIn(joined["parent_span_id"], {s.parent_id for s in members})


class V1InboundHeadersTest(unittest.TestCase):
    """v1 with OTEL_IGNORE_CONTEXT_PROPAGATION=true, headers and joined scenarios (1.105.1, content off)."""

    def setUp(self):
        self.spans, self.meta, _ = fixture("docker-v1-ignore-context")
        self.by_trace = oc.traces(self.spans)

    def test_v1_exports_custom_and_forwarded_headers_with_their_values_even_with_content_off(self):
        """Known gap that v2 does not have: the inbound request headers are copied onto litellm_request."""
        calls = [s for s in self.spans if s.name == "litellm_request" and "CUSTOM_MARK_finalX1" in json.dumps(s.attrs)]
        self.assertEqual(len(calls), 1)
        meta = calls[0].attrs["metadata.requester_metadata"]
        self.assertIn("'x-custom-token': 'CUSTOM_MARK_finalX1'", meta)
        self.assertIn("'x-forwarded-for': '203.0.113.7'", meta)
        self.assertIn("'cookie': '***REDACTED***'", meta)  # LiteLLM redacts the cookie, not the other headers
        self.assertIn("x-custom-token", calls[0].attrs["metadata.requester_custom_headers"])
        # a client-sent X-Api-Key and the Authorization header are not exported
        self.assertFalse(oc.contains(self.spans, "APIKEYHDR_"))
        self.assertFalse(oc.contains(self.spans, "COOKIE_"))
        self.assertFalse(oc.contains(self.spans, "uthorization"))

    def test_v1_ignore_flag_still_joins_the_request_span_but_detaches_the_llm_span(self):
        """OTEL_IGNORE_CONTEXT_PROPAGATION does not do what the PRD (J3) assumed on v1."""
        joined = scenario(self.meta, "joined")
        root = oc.roots(self.by_trace[joined["trace_id"]])[0]
        self.assertEqual(root.name, "Received Proxy Server Request")
        self.assertEqual(root.parent_id, joined["parent_span_id"])  # still a child of the caller
        calls = [s for s in self.spans if s.name == "litellm_request"]
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(len(self.by_trace[call.trace_id]), 1)  # alone in a trace of its own
            self.assertEqual(call.parent_id, "")


class V2IgnoreContextTest(unittest.TestCase):
    def test_the_flag_changes_nothing_on_v2(self):
        spans, meta, _ = fixture("docker-v2-ignore-context")
        joined = scenario(meta, "joined")
        members = oc.traces(spans)[joined["trace_id"]]
        root = oc.roots(members)[0]
        self.assertEqual(root.parent_id, joined["parent_span_id"])
        self.assertEqual(sorted(m.name.split(" ")[0] for m in members), ["POST", "auth", "chat"])


class CheckFunctionTest(unittest.TestCase):
    def test_check_passes_on_the_v2_content_off_capture_and_fails_on_a_missing_project(self):
        import tempfile, shutil
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            for name, content, expect_fail in (("docker-v2-content-off", "off", False), ("docker-v2-no-project", "off", True)):
                meta = json.loads((FIXTURES / f"{name}.meta.json").read_text())
                cap = Path(tmp) / name
                cap.mkdir()
                shutil.copy(FIXTURES / f"{name}.json", cap / "001-traces.json")
                with (cap / "requests.jsonl").open("w") as fh:
                    for r in meta["requests"]:
                        fh.write(json.dumps({**r, "bytes": 1, "user_agent": ""}) + "\n")
                results = oc.check(str(cap), "v2", content, meta["marker"])
                failed = [m for ok, m in results if ok is False]
                if expect_fail:
                    self.assertEqual(len(failed), 1)
                    self.assertIn("project_name", failed[0])
                else:
                    self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
