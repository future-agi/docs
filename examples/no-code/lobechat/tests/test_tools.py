"""Unit tests for the test-run helpers: MCP order tools, agent-run driver, stored-span checks, scanner."""

import json

import pytest

import check_spans
import drive_lobehub
import order_tools
import scan_local_stack


# ---- order_tools (test MCP server) -------------------------------------------------------------------
def test_order_status_is_deterministic():
    out = order_tools.order_status(" ORD-ABC123456 ")
    assert out["order_id"] == "ORD-ABC123456"
    assert out["carrier"] == "ParcelCo"
    assert out["note"].endswith("123456")


def test_cancel_order_always_fails():
    with pytest.raises(order_tools.CancelRefused, match="already shipped"):
        order_tools.cancel_order("ORD-1")


# ---- drive_lobehub ---------------------------------------------------------------------------------------
def test_turns_carry_marker_and_one_provider_failure():
    turns = drive_lobehub.turns("MK1")
    assert [t[0] for t in turns] == ["tool", "tool_fail", "provider"]
    assert all("MK1" in prompt for _, prompt, _ in turns)
    assert [m for _, _, m in turns] == [None, None, "bad"]


def test_trpc_envelope_and_error(monkeypatch):
    lh = drive_lobehub.LobeHub("http://lobe.test/", "k")
    seen = {}

    class Resp:
        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    def fake_post(url, params=None, json=None, timeout=None):
        seen.update(url=url, params=params, body=json)
        return Resp([{"result": {"data": {"json": {"id": "c-1"}}}}])

    monkeypatch.setattr(lh.s, "post", fake_post)
    assert lh.trpc("connector.create", {"identifier": "x"}) == {"id": "c-1"}
    assert seen["url"] == "http://lobe.test/trpc/lambda/connector.create"
    assert seen["params"] == {"batch": "1"}
    assert seen["body"] == {"0": {"json": {"identifier": "x"}}}

    monkeypatch.setattr(lh.s, "post", lambda *a, **k: Resp([{"error": {"message": "nope"}}]))
    with pytest.raises(RuntimeError, match="connector.create failed"):
        lh.trpc("connector.create", {})


def test_driver_requires_exec_key(monkeypatch, capsys):
    monkeypatch.delenv("AGENT_EXEC_API_KEY", raising=False)
    assert drive_lobehub.main(["--model", "m"]) == 2


# ---- check_spans -----------------------------------------------------------------------------------------
def span(name, sid, parent="", kind="chain", status="UNSET", model="", pt=0, ct=0, session="", attrs=None,
         trace="t1", resource=("project_name", "service.name")):
    return {"trace_id": trace, "id": sid, "parent_span_id": parent, "name": name, "observation_type": kind,
            "status": status, "model": model, "prompt_tokens": pt, "completion_tokens": ct,
            "session": session, "attrs": attrs or {}, "resource_keys": list(resource)}


def good_trace():
    return [
        span("tRPC MUTATION aiAgent.execAgent", "r"),
        span("execAgent start_operation", "s", "r"),
        span("invoke_agent Lobe AI", "a", "s", "agent", session="sess"),
        span("chat gpt-x", "c", "a", "llm", model="gpt-x", pt=10, ct=2, session="sess"),
        span("execute_tool ordertools/get_order_status", "t", "a", "tool",
             attrs={"tool.name": "ordertools/get_order_status"}),
        span("context_engineering", "e", "a"),
    ]


def test_check_passes_on_good_trace():
    res = check_spans.check(good_trace(), "gpt-x")
    assert all(p for p, _ in res.values()), {k: v for k, v in res.items() if not v[0]}


@pytest.mark.parametrize("mutate,failing", [
    (lambda ss: ss.append(span("GET /api/x", "x", "r")), "only agent runtime + entry spans"),
    (lambda ss: ss.__setitem__(2, {**ss[2], "parent_span_id": "gone"}), "no orphan spans"),
    (lambda ss: ss.__setitem__(1, {**ss[1], "parent_span_id": ""}), "one root per agent run trace"),
    (lambda ss: ss.__setitem__(2, {**ss[2], "pt": 0, "prompt_tokens": 5}), "tokens counted once"),
    (lambda ss: ss.__setitem__(3, {**ss[3], "observation_type": "agent"}), "span types"),
    (lambda ss: ss.__setitem__(3, {**ss[3], "session": ""}), "session on agent and llm spans"),
    (lambda ss: ss.__setitem__(0, {**ss[0], "resource_keys": ["project_name", "host.name"]}),
     "no host/os/process resource keys"),
])
def test_check_catches_regressions(mutate, failing):
    ss = good_trace()
    mutate(ss)
    res = check_spans.check(ss, "gpt-x")
    assert res[failing][0] is False


def test_check_expect_error():
    ss = good_trace()
    res = check_spans.check(ss, "gpt-x", expect_error=True)
    assert res["ERROR llm span"][0] is False
    ss.append(span("chat bad", "c2", "a2", "llm", status="ERROR", model="bad"))
    ss.append(span("invoke_agent Lobe AI", "a2", "s", "agent", status="ERROR", session="sess"))
    res = check_spans.check(ss, "gpt-x", expect_error=True)
    assert res["ERROR llm span"][0] and res["ERROR agent span"][0]


def test_flatten_resource_keys():
    keys = set(check_spans._flatten_keys({"service": {"name": "lobehub"}, "project_name": "p"}))
    assert keys == {"service.name", "project_name"}


# ---- scan_local_stack ------------------------------------------------------------------------------------
def test_scan_helpers():
    assert scan_local_stack.parse_needle("fi_secret=abc123") == ("fi_secret", "abc123")
    blobs = {"t1": json.dumps({"p": "/Users/me/x"}), "t2": "nothing"}
    assert scan_local_stack.count_needle(blobs, "/Users/me") == {"t1": 1}
