#!/usr/bin/env python3
"""Drive one LibreChat chat turn over LibreChat's own HTTP API, the same calls the web UI makes.

Registers the user if needed, logs in, starts a turn on a custom endpoint (optionally with MCP servers
enabled for the turn), reads the turn's event stream to the end and prints a JSON summary. Standard
library only.

  drive_chat.py --base http://127.0.0.1:13080 --email a@example.test --password ... \
      --endpoint TestModels --model gpt-6-luna --mcp order-tools --text "What is the status of A-1001?"

Calls (LibreChat v0.8.8):
  POST /api/auth/register, POST /api/auth/login             -> bearer token
  POST /api/agents/chat/<endpoint>                           -> {streamId, conversationId, generationCreatedAt}
  GET  /api/agents/chat/stream/<streamId>?...                -> server-sent events until {"final": true}
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT_PARENT = "00000000-0000-0000-0000-000000000000"
# LibreChat's uaParser middleware answers "Illegal request" to clients it does not recognise as a browser,
# so this script presents itself as one, like the web UI does.
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


def _request(method, url, body=None, token=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", BROWSER_UA)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=timeout)


def _decode(raw):
    try:
        return json.loads(raw or b"{}")
    except ValueError:  # LibreChat answers some rejections with a one-event SSE body
        return {"raw": raw[:200].decode(errors="replace")}


def post_json(url, body, token=None):
    try:
        with _request("POST", url, body, token) as resp:
            return resp.status, _decode(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, _decode(err.read())


def login(base, name, username, email, password):
    status, body = post_json(f"{base}/api/auth/login", {"email": email, "password": password})
    if status == 200 and body.get("token"):
        return body
    reg = {"name": name, "username": username, "email": email, "password": password,
           "confirm_password": password}
    status, body = post_json(f"{base}/api/auth/register", reg)
    if status not in (200, 201):
        raise SystemExit(f"register failed: HTTP {status}")
    status, body = post_json(f"{base}/api/auth/login", {"email": email, "password": password})
    if status != 200 or not body.get("token"):
        raise SystemExit(f"login failed: HTTP {status}")
    return body


def build_turn(text, endpoint, model, mcp=None, conversation_id=None, parent_message_id=None):
    """The request body the LibreChat web UI sends for one turn of an ephemeral agent."""
    body = {
        "text": text,
        "sender": "User",
        "isCreatedByUser": True,
        "parentMessageId": parent_message_id or ROOT_PARENT,
        "messageId": str(uuid.uuid4()),
        "error": False,
        "endpoint": endpoint,
        "endpointType": "custom",
        "model": model,
        "key": "never",
        "isTemporary": False,
        "isRegenerate": False,
        "isContinued": False,
        "ephemeralAgent": {"mcp": list(mcp or [])},
        "clientRequestId": str(uuid.uuid4()),
        "generationProtocolVersion": 2,
    }
    if conversation_id:
        body["conversationId"] = conversation_id
    return body


def parse_sse(lines):
    """Yield the JSON payload of every `data:` line of a server-sent event stream."""
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n") if isinstance(raw, bytes) else raw.rstrip("\r\n")
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            yield json.loads(payload)
        except ValueError:
            continue


def summarize(events):
    """Reduce the turn's events to what the test run checks: tools called, usage, final text, errors."""
    out = {"tool_calls": [], "usage_events": 0, "final": False, "error": False,
           "text": "", "conversation_id": None, "response_message_id": None}
    for ev in events:
        name = ev.get("event")
        data = ev.get("data") or {}
        if name == "on_run_step_completed":
            call = (data.get("result") or {}).get("tool_call") or {}
            if call.get("name"):
                out["tool_calls"].append(call["name"])
        elif name == "on_token_usage":
            out["usage_events"] += 1
        if ev.get("error") or name == "error":
            out["error"] = True
        if ev.get("final"):
            out["final"] = True
            resp = ev.get("responseMessage") or {}
            out["conversation_id"] = (ev.get("conversation") or {}).get("conversationId")
            out["response_message_id"] = resp.get("messageId")
            # A failed turn still ends with a final event; the failure is a content part of type "error".
            if resp.get("error") or any(c.get("type") == "error" for c in resp.get("content") or []):
                out["error"] = True
            parts = [c.get("text", "") for c in resp.get("content") or [] if c.get("type") == "text"]
            out["text"] = "".join(parts) or resp.get("text", "")
    return out


def run_turn(base, token, body, timeout=180):
    url = f"{base}/api/agents/chat/{urllib.parse.quote(body['endpoint'])}"
    status, start = post_json(url, body, token)
    if status != 200 or not start.get("streamId"):
        return {"started": False, "http_status": status, "error": True, "final": False}
    q = urllib.parse.urlencode({"generationCreatedAt": start.get("generationCreatedAt", ""),
                                "generationProtocolVersion": 2})
    stream_url = f"{base}/api/agents/chat/stream/{urllib.parse.quote(start['streamId'])}?{q}"
    req = urllib.request.Request(stream_url, headers={"Authorization": f"Bearer {token}",
                                                      "Accept": "text/event-stream",
                                                      "User-Agent": BROWSER_UA})
    events = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for ev in parse_sse(resp):
            events.append(ev)
            if ev.get("final") or ev.get("event") == "error":
                break
    result = summarize(events)
    result.update({"started": True, "http_status": status, "stream_id": start["streamId"]})
    result["conversation_id"] = result["conversation_id"] or start.get("conversationId")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:13080")
    ap.add_argument("--name", default="Test User")
    ap.add_argument("--username", default="testuser")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--endpoint", default="TestModels")
    ap.add_argument("--model", required=True)
    ap.add_argument("--mcp", action="append", default=[])
    ap.add_argument("--text", required=True)
    ap.add_argument("--conversation-id")
    ap.add_argument("--parent-message-id")
    a = ap.parse_args(argv)
    auth = login(a.base, a.name, a.username, a.email, a.password)
    body = build_turn(a.text, a.endpoint, a.model, a.mcp, a.conversation_id, a.parent_message_id)
    result = run_turn(a.base, auth["token"], body)
    result["user_id"] = (auth.get("user") or {}).get("id") or (auth.get("user") or {}).get("_id")
    print(json.dumps(result))
    return 0 if result.get("final") else 1


if __name__ == "__main__":
    sys.exit(main())
