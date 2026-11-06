"""Offline checks of the recorded Embabel 1.5.3 OTLP payload and of the replay tool: python -m pytest tools/tests"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import replay_fixture  # noqa: E402

PAYLOAD = json.loads(replay_fixture.FIXTURE.read_text())


def attrs(items):
    return {a["key"]: next(iter(a["value"].values())) for a in items}


def spans(payload):
    return [sp for rs in payload["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]]


def test_every_batch_carries_project_and_no_host_details():
    for rs in PAYLOAD["resourceSpans"]:
        res = attrs(rs["resource"]["attributes"])
        assert res["project_name"] == "embabel-fixture" and res["project_type"] == "observe"
        assert res["service.name"] == "embabel-weather-agent"
        assert not [k for k in res if k.startswith(("host.", "process.", "os."))]


def test_recorded_tree_matches_the_page():
    by_id = {sp["spanId"]: sp for sp in spans(PAYLOAD)}
    parent = {sp["name"]: by_id.get(sp.get("parentSpanId", ""), {}).get("name") for sp in spans(PAYLOAD)}
    assert parent["agent WeatherAgent"] is None
    assert parent["action report"] == "agent WeatherAgent"
    assert parent["llm gpt-6-luna"] == "action report"
    assert parent["tool-loop"] == "llm gpt-6-luna"
    assert parent["chat gpt-6-luna"] == "tool-loop"
    assert parent["execute_tool currentWeather"] == "tool-loop"
    chat = [attrs(sp["attributes"]) for sp in spans(PAYLOAD) if sp["name"] == "chat gpt-6-luna"]
    assert len(chat) == 2 and all(c["gen_ai.operation.name"] == "chat" and c["gen_ai.usage.input_tokens"] for c in chat)


def test_content_off_recording_has_no_payload_attributes():
    keys = {k for sp in spans(PAYLOAD) for k in attrs(sp.get("attributes", []))}
    for content_key in ("input.value", "output.value", "gen_ai.input.messages", "gen_ai.output.messages",
                        "gen_ai.tool.call.arguments", "gen_ai.tool.call.result", "embabel.agent.result"):
        assert content_key not in keys


def test_replay_copy_gets_fresh_ids_and_keeps_the_tree():
    copy, trace_id = replay_fixture.fresh_copy(PAYLOAD, "replay-project")
    new, old = spans(copy), spans(PAYLOAD)
    assert {sp["traceId"] for sp in new} == {trace_id}
    assert not {sp["spanId"] for sp in new} & {sp["spanId"] for sp in old}
    by_id = {sp["spanId"]: sp["name"] for sp in new}
    assert by_id[next(sp for sp in new if sp["name"] == "action report")["parentSpanId"]] == "agent WeatherAgent"
    assert all(attrs(rs["resource"]["attributes"])["project_name"] == "replay-project" for rs in copy["resourceSpans"])
