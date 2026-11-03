"""Contract test on spans recorded from a REAL aigw v1.2.0 run (tests/fixtures/*.json, see record_fixtures.sh).

Asserts what Future AGI's collector needs: resource project_name, HTTP/protobuf body, both key header
NAMES, OpenInference LLM attributes, session.id from the agent-session-id header, content redaction, and
ERROR status on a failed upstream call. Fixtures contain header names only, never values."""
import json, pathlib

FX = pathlib.Path(__file__).parent / "fixtures"
MARKER = "FIXTURE_PROMPT_MARKER"


def load(name):
    reqs = json.loads((FX / f"{name}.json").read_text())
    traces = [r for r in reqs if r["path"].endswith("/v1/traces")]
    spans, resources = [], []
    for r in traces:
        for rs in r["request"]["resourceSpans"]:
            resources.append({a["key"]: next(iter(a["value"].values())) for a in rs["resource"]["attributes"]})
            for ss in rs["scopeSpans"]:
                for s in ss["spans"]:
                    s["_attrs"] = {a["key"]: next(iter(a["value"].values())) for a in s["attributes"]}
                    spans.append(s)
    return traces, resources, spans


def by_name(spans, name, ok=True):
    return [s for s in spans if s["name"] == name and ((s.get("status", {}).get("code") != "STATUS_CODE_ERROR") == ok)]


def test_only_trace_posts_http_protobuf_with_key_headers_and_no_metrics_or_logs():
    for name in ("content_off", "content_on"):
        reqs = json.loads((FX / f"{name}.json").read_text())
        assert reqs and all(r["path"] == "/v1/traces" for r in reqs)           # no /v1/metrics, no /v1/logs
        assert all(r["content_type"] == "application/x-protobuf" for r in reqs)
        assert all(not r["content_encoding"] for r in reqs)                      # uncompressed, as the recipe sends them
        assert all({"x-api-key", "x-secret-key"} <= set(r["header_names"]) for r in reqs)


def test_every_resource_carries_project_name():
    for name in ("content_off", "content_on"):
        _, resources, _ = load(name)
        assert resources and all(r.get("project_name") == "fixture-project" and r.get("project_type") == "observe" for r in resources)


def test_chat_and_completion_spans_are_openinference_llm_with_model_and_tokens():
    _, _, spans = load("content_off")
    chat, comp = by_name(spans, "ChatCompletion")[0], by_name(spans, "Completion")[0]
    for s in (chat, comp):
        a = s["_attrs"]
        assert a["openinference.span.kind"] == "LLM" and a["llm.model_name"] and a["llm.system"] == "openai"
        assert int(a["llm.token_count.prompt"]) > 0 and int(a["llm.token_count.total"]) >= int(a["llm.token_count.prompt"])


def test_session_header_maps_to_session_id_and_unmapped_headers_are_not_exported():
    _, _, spans = load("content_off")
    chat = by_name(spans, "ChatCompletion")[0]["_attrs"]
    assert chat["session.id"] == "fixture-session"
    assert not any("tenant" in k for k in chat)        # x-tenant-id was sent but never mapped


def test_content_off_exports_no_prompt_or_response_text():
    raw = (FX / "content_off.json").read_text()
    assert MARKER not in raw
    _, _, spans = load("content_off")
    for s in spans:
        a = s["_attrs"]
        assert a["input.value"] == "__REDACTED__" and a.get("output.value", "__REDACTED__") == "__REDACTED__"
        assert not any(k.startswith(("llm.input_messages", "llm.output_messages", "llm.prompts", "llm.choices")) for k in a)


def test_content_on_opt_in_exports_the_prompt():
    _, _, spans = load("content_on")
    chat = by_name(spans, "ChatCompletion")[0]["_attrs"]
    assert chat["llm.input_messages.0.message.content"] == MARKER


def test_failed_upstream_call_is_an_error_span():
    _, _, spans = load("content_off")
    err = by_name(spans, "ChatCompletion", ok=False)
    assert err and err[0]["status"]["code"] == "STATUS_CODE_ERROR"
    assert err[0]["status"]["message"].startswith("Error code: 400")
