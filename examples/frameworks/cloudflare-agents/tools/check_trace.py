#!/usr/bin/env python3
"""Check the stored span tree (the list fi_verify.py --json writes).

    check_trace.py spans.json happy|tool-error|model-error [--model gpt-6-luna] [--traces id,id]

happy        every turn: root POST (chain, session) > ... > POST (the Agent's invocation, chain) > invoke_agent (agent,
             no own token usage) > chat (llm, model, tokens) + execute_tool (tool) > tool_approval (chain, approved);
             every agent-side span in the trace's one session; no ERROR; no Durable Object storage spans
tool-error   as happy, but execute_tool is ERROR with message "Error" (the class name, not the text)
model-error  invoke_agent and chat are ERROR with message "AI_APICallError"; no execute_tool. Runtime spans (POST, fetch)
             may be ERROR too, with no message: a deployed Worker marks 5xx responses and failed fetches ERROR
             (seen in the real Cloudflare export, not in local workerd).
Prints trace ids. Exit 1 on the first failed check.
"""
import argparse
import json
import sys

NO_SESSION = ("", None, "None", "00000000-0000-0000-0000-000000000000")


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


def check(spans, mode, model):
    by_id = {s["id"]: s for s in spans}
    kind = lambda s: s["name"].split(" ", 1)[0]
    if any(s["name"].startswith("durable_object_storage_") for s in spans):
        fail("Durable Object storage spans were stored (the collector filter did not run)")
    agents = [s for s in spans if kind(s) == "invoke_agent"]
    if not agents:
        fail("no invoke_agent span")
    for tid in {s["trace_id"] for s in spans}:
        ts = [s for s in spans if s["trace_id"] == tid]
        roots = [s for s in ts if s["parent_span_id"] not in by_id]
        if len(roots) != 1 or roots[0]["name"] != "POST" or roots[0]["observation_type"] != "chain":
            fail(f"trace {tid}: roots {[r['name'] for r in roots]}, want one POST (chain)")
        root_session = roots[0]["session"]
        if root_session in NO_SESSION:
            fail(f"trace {tid}: the root span has no session (the Worker did not set gen_ai.conversation.id)")
        sessions = {s["session"] for s in ts if s["session"] not in NO_SESSION}
        if sessions != {root_session}:
            fail(f"trace {tid}: {len(sessions)} sessions, want the root's one")
    for a in agents:
        if a["observation_type"] != "agent":
            fail(f"invoke_agent stored as {a['observation_type']}")
        parent = by_id.get(a["parent_span_id"])
        if not parent or parent["name"] != "POST" or parent["observation_type"] != "chain":
            fail(f"invoke_agent parent is {parent and parent['name']!r}, want the Agent's POST invocation (chain)")
        if a["prompt_tokens"] or a["completion_tokens"] or a["total_tokens"]:
            fail("invoke_agent carries token usage (session totals would count the turn twice)")
        if a["attrs_string"].get("gen_ai.agent.name") != "weather-agent":
            fail("invoke_agent has no gen_ai.agent.name=weather-agent")
        kids = [s for s in spans if s["parent_span_id"] == a["id"]]
        chats = [s for s in kids if kind(s) == "chat"]
        tools = [s for s in kids if kind(s) == "execute_tool"]
        if not chats:
            fail("no chat child under invoke_agent")
        for c in chats:
            if c["observation_type"] != "llm":
                fail(f"chat stored as {c['observation_type']}")
            if not (c["model"] or "").startswith(model):  # the response model may carry a date suffix
                fail(f"chat model {c['model']!r}, want {model!r}")
        if mode in ("happy", "tool-error"):
            if not tools:
                fail("no execute_tool child under invoke_agent")
            if not all(c["prompt_tokens"] and c["completion_tokens"] for c in chats):
                fail("token counts missing on a chat span")
            for t in tools:
                if t["observation_type"] != "tool":
                    fail(f"execute_tool stored as {t['observation_type']}")
                approvals = [s for s in spans if s["parent_span_id"] == t["id"] and kind(s) == "tool_approval"]
                if len(approvals) != 1 or approvals[0]["observation_type"] != "chain":
                    fail(f"execute_tool has {len(approvals)} tool_approval children (want one, chain)")
                if approvals[0]["attrs_string"].get("cloudflare.agents.tool.approval.state") != "approved":
                    fail("tool_approval state is not approved")
        elif tools:
            fail("execute_tool ran although the model call failed")
    errors = sorted((s["name"], s["status_message"]) for s in spans if s["status"] == "ERROR")
    if mode == "happy" and errors:
        fail(f"unexpected ERROR spans {errors}")
    if mode == "tool-error":
        if not errors or any(n != "execute_tool get_weather" or m != "Error" for n, m in errors):
            fail(f"ERROR spans {errors}, want execute_tool get_weather / Error")
    if mode == "model-error":
        names = {n for n, _ in errors}
        if "invoke_agent weather-agent" not in names or not any(n.startswith("chat ") for n in names):
            fail(f"ERROR spans {errors}, want invoke_agent and chat")
        runtime = [(n, m) for n, m in errors if n in ("POST", "fetch")]
        genai = [(n, m) for n, m in errors if (n, m) not in runtime]
        if any(m != "AI_APICallError" for _, m in genai):
            fail(f"error messages {genai}, want AI_APICallError only on the GenAI spans")
        if any(m not in ("", "error") for _, m in runtime):
            fail(f"runtime ERROR spans carry a message {runtime}, want none (no error text)")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spans")
    ap.add_argument("mode", choices=["happy", "tool-error", "model-error"])
    ap.add_argument("--model", default="gpt-6-luna")
    ap.add_argument("--traces", default="", help="only these trace ids (comma separated); default all")
    a = ap.parse_args()
    spans = json.load(open(a.spans))
    if a.traces:
        wanted = {t.strip().replace("-", "") for t in a.traces.split(",") if t.strip()}
        spans = [s for s in spans if s["trace_id"].replace("-", "") in wanted]
    if not spans:
        fail("no stored spans for the requested traces")
    errors = check(spans, a.mode, a.model)
    traces = sorted({s["trace_id"] for s in spans})
    turns = sum(1 for s in spans if s["name"].startswith("invoke_agent "))
    print(f"OK {a.mode}: {len(traces)} trace(s), {len(spans)} spans, {turns} turn(s), ERROR={errors}")
    print("trace_ids", ",".join(traces))


if __name__ == "__main__":
    main()
