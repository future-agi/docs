#!/usr/bin/env python3
"""Check the stored span tree (the list fi_verify.py --json writes).

    check_trace.py spans.json happy|tool-error|model-error [--model gpt-6-luna] [--traces id,id]

happy        every turn: chat_turn > invoke_agent (agent, no own token usage) > chat (llm, model, tokens) +
             execute_tool (tool); no ERROR; a session; no Durable Object storage spans
tool-error   as happy, but execute_tool is ERROR with message "Error" (the class name, not the text)
model-error  invoke_agent and chat are ERROR with message "AI_APICallError"; no execute_tool
Prints trace ids. Exit 1 on the first failed check.
"""
import argparse
import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spans")
    ap.add_argument("mode", choices=["happy", "tool-error", "model-error"])
    ap.add_argument("--model", default="gpt-6-luna")
    ap.add_argument("--traces", default="", help="only these trace ids (comma separated); default all")
    a = ap.parse_args()
    spans, mode, model = json.load(open(a.spans)), a.mode, a.model
    if a.traces:
        wanted = {t.strip().replace("-", "") for t in a.traces.split(",") if t.strip()}
        spans = [s for s in spans if s["trace_id"].replace("-", "") in wanted]
    if not spans:
        fail("no stored spans for the requested traces")
    by_id = {s["id"]: s for s in spans}
    kind = lambda s: s["name"].split(" ", 1)[0]
    if any(s["name"].startswith("durable_object_storage_") for s in spans):
        fail("Durable Object storage spans were stored (the collector filter did not run)")
    agents = [s for s in spans if kind(s) == "invoke_agent"]
    if not agents:
        fail("no invoke_agent span")
    for a in agents:
        if a["observation_type"] != "agent":
            fail(f"invoke_agent stored as {a['observation_type']}")
        parent = by_id.get(a["parent_span_id"])
        if not parent or parent["name"] != "chat_turn" or parent["observation_type"] != "chain":
            fail(f"invoke_agent parent is {parent and parent['name']!r}, want chat_turn (chain)")
        if not a["session"] or a["session"] == "00000000-0000-0000-0000-000000000000":
            fail("no session on the trace")
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
            for t in tools:
                if t["observation_type"] != "tool":
                    fail(f"execute_tool stored as {t['observation_type']}")
            if not all(c["prompt_tokens"] and c["completion_tokens"] for c in chats):
                fail("token counts missing on a chat span")
        if a["prompt_tokens"] or a["completion_tokens"] or a["total_tokens"]:
            fail("invoke_agent carries token usage (session totals would count the turn twice)")
    errors = sorted((s["name"], s["status_message"]) for s in spans if s["status"] == "ERROR")
    if mode == "happy" and errors:
        fail(f"unexpected ERROR spans {errors}")
    if mode == "tool-error":
        if not errors or any(n != "execute_tool lookup_order" or m != "Error" for n, m in errors):
            fail(f"ERROR spans {errors}, want execute_tool lookup_order / Error")
    if mode == "model-error":
        names = {n for n, _ in errors}
        if not {"invoke_agent support-chat"} <= names or not any(n.startswith("chat ") for n in names):
            fail(f"ERROR spans {errors}, want invoke_agent and chat")
        if any(m != "AI_APICallError" for _, m in errors):
            fail(f"error messages {errors}, want AI_APICallError only")
    traces = sorted({s["trace_id"] for s in spans})
    print(f"OK {mode}: {len(traces)} trace(s), {len(spans)} spans, {len(agents)} turn(s), ERROR={errors}")
    print("trace_ids", ",".join(traces))


if __name__ == "__main__":
    main()
