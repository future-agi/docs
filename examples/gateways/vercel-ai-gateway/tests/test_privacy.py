"""Content capture: what the span export contains by default, and with it switched off.

The marker is unique per run and is placed in the system prompt, the user prompt, and
(through the stand-in's echo) the model answer, the tool-call arguments and the tool
result. The search covers every byte the collector received and every decoded span
attribute, event and resource attribute."""
import json
import uuid

from conftest import MODEL

HIDE_ALL = {"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true", "FI_HIDE_LLM_INVOCATION_PARAMETERS": "true"}


def marker():
    return f"MARKER-{uuid.uuid4().hex[:12]}"


def run_with_marker(run_app, env=None):
    m = marker()
    result = run_app("--prompt", f"find {m}", "--system", f"system note {m}", env=env)
    assert result.returncode == 0, result.stderr[-1500:]
    # the application itself still gets the full answer, tool call and tool result
    assert f"RESULT chat: echo: find {m}" in result.stdout
    assert f"RESULT tools: echo: record for find {m}" in result.stdout
    return m


def all_exported_text(collector):
    chunks = list(collector.raw_texts())
    for span in collector.spans():
        chunks.append(json.dumps(span["_resource"]))
        chunks.append(json.dumps(span["_attrs"]))
        chunks.append(json.dumps(span.get("events", [])))
        chunks.append(json.dumps(span.get("status", {})))
    return "\n".join(chunks)


def test_prompts_and_answers_are_captured_by_default(run_app, collector):
    m = run_with_marker(run_app)
    text = all_exported_text(collector)
    assert text.count(m) >= 8, "default capture should include prompts, answers, tool arguments and results"


def test_hiding_inputs_and_outputs_keeps_the_marker_out_of_every_exported_byte(run_app, collector):
    m = run_with_marker(run_app, env=HIDE_ALL)
    assert collector.exports
    assert m not in all_exported_text(collector)
    # the spans are still useful: model and usage survive on the non-streaming calls
    chat = sorted((s for s in collector.spans() if s["_attrs"].get("gen_ai.span.kind") == "LLM"),
                  key=lambda s: int(s["start_time_unix_nano"]))[0]
    assert chat["_attrs"]["gen_ai.request.model"] == MODEL
    assert int(chat["_attrs"]["gen_ai.usage.input_tokens"]) > 0
    assert chat["_attrs"]["input.value"] == "__REDACTED__"


def test_invocation_parameters_follow_their_own_flag(run_app, collector):
    run_with_marker(run_app, env={"FI_HIDE_INPUTS": "true", "FI_HIDE_OUTPUTS": "true"})
    assert any("gen_ai.request.parameters" in s["_attrs"] for s in collector.spans())
    collector.exports.clear()
    run_with_marker(run_app, env=HIDE_ALL)
    assert not any("gen_ai.request.parameters" in s["_attrs"] for s in collector.spans())


def test_documented_residue_of_the_hide_flags(run_app, collector):
    """What FI_HIDE_* does NOT remove on traceai-openai 0.1.10. The docs page lists each of
    these. If one of these assertions starts failing the instrumentor got better: update the
    page's privacy section."""
    run_with_marker(run_app, env=HIDE_ALL)
    spans = collector.spans()
    # developer-authored tool definitions (name, description, JSON schema)
    assert any("Look up a record" in s["_attrs"].get("gen_ai.tool.definitions", "") for s in spans)
    # session id
    assert all(s["_attrs"].get("session.id") for s in spans)
    # error text: status message and exception event (type, message, stack trace)
    failed = [s for s in spans if s.get("status", {}).get("code") == "STATUS_CODE_ERROR"]
    messages = " ".join(s["status"]["message"] for s in failed)
    assert len(failed) == 2 and "401" in messages and "404" in messages
    # the 404 body names the model id that was sent
    assert "does-not-exist/no-such-model" in messages
    for span in failed:
        exc = [e for e in span["events"] if e["name"] == "exception"][0]
        keys = {a["key"] for a in exc["attributes"]}
        assert {"exception.type", "exception.message", "exception.stacktrace"} <= keys
