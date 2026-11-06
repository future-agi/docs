"""Lifecycle contract of the recipe. No network beyond 127.0.0.1, no AWS client, no credentials."""
import time

import pytest
from conftest import Collector, FakeContext, RecordingExporter, fixture

import tracing


def test_provider_built_once_across_invocations(load_handler):
    log = []
    tracing.init(RecordingExporter(log), set_global=False)
    h = load_handler()
    h.lambda_handler({"order_id": "A-1"}, FakeContext())
    h.lambda_handler({"order_id": "A-2"}, FakeContext())
    assert tracing.providers_built == 1


def test_flush_before_return_on_success_and_error(load_handler):
    log = []
    exp = RecordingExporter(log)
    tracing.init(exp, set_global=False)
    h = load_handler()
    h.lambda_handler({"order_id": "A-1"}, FakeContext())
    log.append(("returned", None))
    with pytest.raises(ValueError):
        h.lambda_handler({"order_id": "boom"}, FakeContext())
    log.append(("raised", None))
    kinds = [e[0] for e in log]
    # the batch timer is 60 s: exports can only have come from the explicit flush
    assert kinds == ["export", "returned", "export", "raised"]
    assert sorted(log[0][1]) == ["lambda.handler", "lookup_order"]


def test_warm_start_is_a_new_trace_and_nothing_stays_open(load_handler):
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    h.lambda_handler({"order_id": "A-1"}, FakeContext())
    h.lambda_handler({"order_id": "A-2"}, FakeContext())
    roots = [s for s in exp.spans if s.name == "lambda.handler"]
    assert len(roots) == 2 and roots[0].context.trace_id != roots[1].context.trace_id
    assert [r.attributes["faas.coldstart"] for r in roots] == [True, False]
    assert len(exp.spans) == 4  # root + tool per invocation, all ended


def test_error_path_marks_error_and_still_returns_through_flush(load_handler):
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    with pytest.raises(ValueError):
        h.lambda_handler({"order_id": "boom", "note": "SECRET-NOTE"}, FakeContext())
    by = {s.name: s for s in exp.spans}
    assert by["lambda.handler"].status.status_code.name == "ERROR"
    assert by["lookup_order"].status.status_code.name == "ERROR"
    assert by["lambda.handler"].status.description == "ValueError"  # type only by default
    assert by["lambda.handler"].events == ()                         # no exception event, no stack trace


def test_unset_keys_do_not_fail_and_export_nothing(load_handler, caplog, monkeypatch):
    monkeypatch.setenv("FI_PROJECT_NAME", "ENV-VALUE-MARKER")
    h = load_handler()  # no exporter injected, no FI_* env
    assert h.lambda_handler({"order_id": "A-1"}, FakeContext())["status"] == "shipped"
    assert tracing.init()._active_span_processor._span_processors == ()
    assert sum("not set" in r.message for r in caplog.records) == 1
    assert "ENV-VALUE-MARKER" not in "".join(r.message for r in caplog.records)  # does not echo the environment


def test_only_one_key_set_is_still_off(load_handler, monkeypatch):
    monkeypatch.setenv("FI_API_KEY", "k")
    h = load_handler()
    h.lambda_handler({"order_id": "A-1"}, FakeContext())
    assert tracing.init()._active_span_processor._span_processors == ()


def test_headers_resource_path_and_no_gzip(load_handler, monkeypatch, collector):
    monkeypatch.setenv("FI_API_KEY", "key-1")
    monkeypatch.setenv("FI_SECRET_KEY", "secret-1")
    monkeypatch.setenv("FI_BASE_URL", collector.url)
    monkeypatch.setenv("FI_PROJECT_NAME", "lambda-test")
    h = load_handler()
    h.lambda_handler({"order_id": "A-1"}, FakeContext())
    (req,) = collector.requests
    assert req["path"] == "/tracer/v1/traces"
    assert req["headers"]["x-api-key"] == "key-1" and req["headers"]["x-secret-key"] == "secret-1"
    assert "content-encoding" not in req["headers"]
    res = {kv.key: kv.value.string_value for kv in collector.decoded()[0].resource_spans[0].resource.attributes}
    assert res["project_name"] == "lambda-test" and res["project_type"] == "observe"
    assert "faas.name" not in res  # AWS_LAMBDA_FUNCTION_NAME unset: no invented name
    assert not any(k.startswith("host.") for k in res)


def test_faas_name_only_from_the_environment(load_handler, monkeypatch, collector):
    monkeypatch.setenv("FI_API_KEY", "k")
    monkeypatch.setenv("FI_SECRET_KEY", "s")
    monkeypatch.setenv("FI_BASE_URL", collector.url)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "orders-fn")
    h = load_handler()
    h.lambda_handler({"order_id": "A-1"}, FakeContext())
    res = {kv.key: kv.value.string_value for kv in collector.decoded()[0].resource_spans[0].resource.attributes}
    assert res["faas.name"] == "orders-fn" and res["project_name"] == "orders-fn"


def test_event_body_is_not_exported_by_default(load_handler):
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    ev = fixture("apigw_v2.json")
    ev["body"] = '{"order_id": "A-1", "note": "BODY-MARKER"}'
    h.lambda_handler(ev, FakeContext())
    dump = repr([(s.name, dict(s.attributes), s.status.description, s.events) for s in exp.spans])
    assert "BODY-MARKER" not in dump and "input.value" not in dump and "output.value" not in dump


def test_opt_in_exports_event_result_and_error_message(load_handler, monkeypatch):
    monkeypatch.setenv("LAMBDA_TRACE_CAPTURE_CONTENT", "true")
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    h.lambda_handler({"order_id": "A-1", "note": "OPT-IN-MARKER"}, FakeContext())
    with pytest.raises(ValueError):
        h.lambda_handler({"order_id": "boom", "note": "OPT-IN-ERR"}, FakeContext())
    dump = repr([(s.name, dict(s.attributes), s.status.description, [dict(e.attributes) for e in s.events]) for s in exp.spans])
    assert "OPT-IN-MARKER" in dump and "OPT-IN-ERR" in dump
    assert "Traceback" not in dump and "stacktrace" not in dump and "/" + "Users" not in dump


def test_api_gateway_v2_traceparent_parents_the_root(load_handler):
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    h.lambda_handler(fixture("apigw_v2.json"), FakeContext())
    root = next(s for s in exp.spans if s.name == "lambda.handler")
    assert format(root.context.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert format(root.parent.span_id, "016x") == "00f067aa0ba902b7"
    tool = next(s for s in exp.spans if s.name == "lookup_order")
    assert tool.parent.span_id == root.context.span_id


def test_sqs_event_starts_a_new_trace(load_handler):
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    h.lambda_handler(fixture("sqs.json"), FakeContext())
    root = next(s for s in exp.spans if s.name == "lambda.handler")
    assert root.parent is None
    assert format(root.context.trace_id, "032x") != "4bf92f3577b34da6a3ce929d0e0e4736"


def test_v1_rest_api_event_and_garbage_traceparent_are_not_extracted(load_handler):
    exp = RecordingExporter([])
    tracing.init(exp, set_global=False)
    h = load_handler()
    h.lambda_handler({"headers": {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}}, FakeContext())
    bad = fixture("apigw_v2.json")
    bad["headers"]["traceparent"] = "not-a-traceparent"
    h.lambda_handler(bad, FakeContext())
    assert all(s.parent is None for s in exp.spans if s.name == "lambda.handler")


def test_exporter_failure_never_fails_the_invocation(load_handler, monkeypatch):
    c = Collector(status=503)
    monkeypatch.setenv("FI_API_KEY", "k")
    monkeypatch.setenv("FI_SECRET_KEY", "s")
    monkeypatch.setenv("FI_BASE_URL", c.url)
    try:
        h = load_handler()
        t = time.monotonic()
        assert h.lambda_handler({"order_id": "A-1"}, FakeContext())["status"] == "shipped"
        assert time.monotonic() - t < 3.5  # bounded by the flush budget, not by exporter retries
    finally:
        c.close()


def test_unreachable_endpoint_never_fails_the_invocation(load_handler, monkeypatch):
    monkeypatch.setenv("FI_API_KEY", "k")
    monkeypatch.setenv("FI_SECRET_KEY", "s")
    monkeypatch.setenv("FI_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    h = load_handler()
    t = time.monotonic()
    assert h.lambda_handler({"order_id": "A-1"}, FakeContext())["status"] == "shipped"
    assert time.monotonic() - t < 3.5


def test_flush_budget_is_shorter_than_remaining_time(load_handler, monkeypatch):
    c = Collector(delay=5)  # a collector that answers too late
    monkeypatch.setenv("FI_API_KEY", "k")
    monkeypatch.setenv("FI_SECRET_KEY", "s")
    monkeypatch.setenv("FI_BASE_URL", c.url)
    try:
        h = load_handler()
        t = time.monotonic()
        h.lambda_handler({"order_id": "A-1"}, FakeContext(remaining_ms=1000))  # 1 s left: 0.75 s budget
        assert time.monotonic() - t < 1.0
    finally:
        c.close()


def test_flush_skipped_when_no_time_is_left(load_handler, caplog):
    log = []
    tracing.init(RecordingExporter(log), set_global=False)
    h = load_handler()
    assert h.lambda_handler({"order_id": "A-1"}, FakeContext(remaining_ms=100))["status"] == "shipped"
    assert log == []  # nothing exported: the skip is logged, not hidden
    assert any("flush skipped" in r.message for r in caplog.records)


def test_cancelled_invocation_still_attempts_flush(load_handler):
    log = []
    tracing.init(RecordingExporter(log), set_global=False)
    h = load_handler()

    class Boom(BaseException):  # e.g. a runtime-injected timeout signal
        pass

    import handler as hmod
    orig = hmod.lookup_order
    hmod.lookup_order = lambda *a, **k: (_ for _ in ()).throw(Boom())
    try:
        with pytest.raises(Boom):
            h.lambda_handler({"order_id": "A-1"}, FakeContext())
    finally:
        hmod.lookup_order = orig
    assert [e[0] for e in log] == ["export"]
