"""What leaves the process, and what the standard traceAI hide settings keep out.

A unique marker is placed in the system prompt and the user prompt. The stand-in echoes it into
the model answer, the tool-call arguments and (through the app's tool) the tool result, so it
travels through every field a real conversation fills. The recording collector sees every byte
the process exports."""
import json
import uuid

from conftest import kind, llm_spans

HIDE = {
    "FI_HIDE_INPUTS": "true",
    "FI_HIDE_OUTPUTS": "true",
    "FI_HIDE_LLM_INVOCATION_PARAMETERS": "true",
}


def run_with_marker(run_app, env=None):
    marker = f"ZMARK-{uuid.uuid4().hex}"
    result = run_app("--prompt", f"find {marker}", "--system", f"system note {marker}", env=env)
    assert result.returncode == 0, result.stderr[-1500:]
    return marker, result


def test_content_is_captured_by_default(run_app, collector):
    marker, _ = run_with_marker(run_app)
    exported = "\n".join(collector.raw_texts())
    assert exported.count(marker) > 0
    spans = llm_spans(collector)
    attrs = [s["_attrs"] for s in spans]
    # system prompt, user prompt, answers, tool arguments and tool result all carry the marker
    joined = lambda key: " ".join(str(a.get(key, "")) for a in attrs)  # noqa: E731
    assert f"system note {marker}" in joined("gen_ai.input.messages.0.message.content")
    assert marker in joined("gen_ai.input.messages.1.message.content")
    assert marker in joined("output.value")
    assert marker in joined("gen_ai.output.messages.0.message.tool_calls.0.tool_call.function.arguments")
    assert marker in joined("gen_ai.input.messages.3.message.content")  # the tool result, in the second tool-round call


def test_hide_settings_keep_the_marker_out_of_every_exported_byte(run_app, collector):
    marker, _ = run_with_marker(run_app, env=HIDE)
    for text in collector.raw_texts():
        assert marker not in text
    assert collector.exports, "spans must still be exported"
    for span in llm_spans(collector):
        a = span["_attrs"]
        assert a.get("input.value") in (None, "__REDACTED__")
        assert a.get("output.value") in (None, "__REDACTED__")
        assert "gen_ai.request.parameters" not in a
        assert all(v == "__REDACTED__" for k, v in a.items() if k.startswith("gen_ai.input.messages.") and k.endswith(".content"))


def test_hide_settings_keep_the_model_tokens_status_and_timing(run_app, collector):
    run_with_marker(run_app, env=HIDE)
    ok = [s for s in llm_spans(collector) if s["status"]["code"] == "STATUS_CODE_OK"]
    assert ok
    for span in ok:
        a = span["_attrs"]
        assert int(a["gen_ai.usage.total_tokens"]) > 0
        assert a["gen_ai.provider.name"] == "openai"
        assert int(span["end_time_unix_nano"]) > int(span["start_time_unix_nano"])
    assert any(s["_attrs"].get("gen_ai.request.model") == "glm-test-model" for s in ok)
    assert any(s["status"]["code"] == "STATUS_CODE_ERROR" for s in llm_spans(collector))


def test_the_opt_in_is_just_unsetting_the_variables(run_app, collector):
    marker, _ = run_with_marker(run_app, env={k: "false" for k in HIDE})
    assert marker in "\n".join(collector.raw_texts())


def test_what_the_hide_settings_do_not_remove(run_app, collector):
    """Pinned so the docs page stays honest about traceAI-openai 0.1.10."""
    run_with_marker(run_app, env=HIDE)
    spans = llm_spans(collector)
    with_tools = [s for s in spans if s["_attrs"].get("gen_ai.tool.definitions") not in (None, "null")]
    assert with_tools, "tool definitions are still exported"
    assert json.loads(with_tools[0]["_attrs"]["gen_ai.tool.definitions"])[0]["function"]["name"] == "lookup_record"
    assert all(s["_attrs"].get("session.id") for s in collector.spans()), "the session id you set is still exported"
    (error_span,) = [s for s in spans if s["status"]["code"] == "STATUS_CODE_ERROR"]
    assert "AuthenticationError" in error_span["status"]["message"], "error text is still exported"
    (event,) = error_span.get("events", [])
    assert event["name"] == "exception"
    # the exception event travels with its message and a stack trace that names local files. If this starts
    # failing, traceai-openai changed: update the Privacy section of the docs page.
    attrs = {a["key"]: a["value"].get("string_value", "") for a in event["attributes"]}
    assert "Traceback" in attrs["exception.stacktrace"]
    assert "site-packages" in attrs["exception.stacktrace"]
    assert "AuthenticationError" in attrs["exception.type"] + attrs["exception.message"] or "401" in attrs["exception.message"]
