#!/usr/bin/env python3
"""Drive real LobeHub agent runs for the E2E test (test scaffolding, not part of the integration).

Uses only LobeHub's own HTTP surface:
  - Better Auth email sign-up (a fresh test user per run),
  - tRPC to add the test MCP server as a connector, pin it to the inbox agent and set the model,
  - POST /api/agent (Bearer AGENT_EXEC_API_KEY) to start server-side agent runs,
  - tRPC aiAgent.getOperationStatus to wait for each run to finish.

Turns:
  tool      the agent calls get_order_status on the MCP server, then answers
  tool_fail the agent calls cancel_order, which always fails (LobeHub returns the error to the model)
  provider  the agent's model does not exist upstream, so the LLM call fails (ERROR span)

The agent description is set to "Order helper for tests <marker>-DESC" (privacy scan needle).

Prints one JSON object: {"user_id", "agent_id", "runs": [{"turn", "operation_id", "topic_id",
"status", "marker"}...]}. Exit code 0 when every run reached a terminal state.

Env: AGENT_EXEC_API_KEY (required).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import requests

TERMINAL = {"done", "error", "interrupted", "max_steps", "cost_limit", "waiting_for_human"}


class LobeHub:
    def __init__(self, base_url: str, exec_key: str, timeout: float = 30.0):
        self.base = base_url.rstrip("/")
        self.exec_key = exec_key
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["Origin"] = self.base

    # -- auth -----------------------------------------------------------------------------------
    def sign_up(self, email: str, password: str, name: str) -> str:
        r = self.s.post(
            f"{self.base}/api/auth/sign-up/email",
            json={"email": email, "password": password, "name": name},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["user"]["id"]

    # -- tRPC (superjson batch envelope) ----------------------------------------------------------
    def trpc(self, path: str, payload: dict, query: bool = False):
        url = f"{self.base}/trpc/lambda/{path}"
        envelope = {"0": {"json": payload}}
        if query:
            r = self.s.get(url, params={"batch": "1", "input": json.dumps(envelope)}, timeout=self.timeout)
        else:
            r = self.s.post(url, params={"batch": "1"}, json=envelope, timeout=self.timeout)
        body = r.json()
        item = body[0] if isinstance(body, list) else body
        if "error" in item:
            raise RuntimeError(f"tRPC {path} failed: {json.dumps(item['error'])[:300]}")
        return item["result"]["data"]["json"]

    def inbox_agent(self) -> dict:
        return self.trpc("agent.getBuiltinAgent", {"slug": "inbox"}, query=True)

    def add_mcp_connector(self, identifier: str, url: str) -> str:
        created = self.trpc(
            "connector.create",
            {
                "identifier": identifier,
                "name": identifier,
                "sourceType": "custom",
                "mcpConnectionType": "http",
                "mcpServerUrl": url,
            },
        )
        connector_id = created["id"] if isinstance(created, dict) else created
        self.trpc("connector.syncTools", {"id": connector_id})
        return connector_id

    def configure_agent(self, agent_id: str, **value) -> None:
        self.trpc("agent.updateAgentConfig", {"agentId": agent_id, "value": value})

    # -- runs -----------------------------------------------------------------------------------
    def exec_agent(self, user_id: str, agent_id: str, prompt: str) -> dict:
        r = requests.post(
            f"{self.base}/api/agent",
            headers={"Authorization": f"Bearer {self.exec_key}"},
            json={"userId": user_id, "agentId": agent_id, "prompt": prompt},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def wait(self, operation_id: str, deadline_s: float = 120.0) -> str:
        end = time.time() + deadline_s
        status = "unknown"
        while time.time() < end:
            try:
                st = self.trpc("aiAgent.getOperationStatus", {"operationId": operation_id}, query=True)
            except RuntimeError:
                st = None
            if isinstance(st, dict):
                status = st.get("status") or (st.get("currentState") or {}).get("status") or status
                if status in TERMINAL:
                    return status
            time.sleep(2)
        return status


def turns(marker: str) -> list[tuple[str, str, str | None]]:
    """(turn name, prompt, model override) — prompts carry the unique marker for the privacy scan."""
    order = f"ORD-{marker}"
    return [
        ("tool", f"Use the get_order_status tool for order {order} and tell me the carrier. Ref {marker}.", None),
        ("tool_fail", f"Use the cancel_order tool to cancel order {order}. Ref {marker}.", None),
        ("provider", f"Say hello. Ref {marker}.", "bad"),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://localhost:3210")
    ap.add_argument("--mcp-url", default="http://host.docker.internal:8790/mcp",
                    help="MCP server URL as LobeHub (inside Docker) reaches it")
    ap.add_argument("--model", required=True)
    ap.add_argument("--bad-model", default="th8280-missing-model")
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--marker", default=None)
    ap.add_argument("--only", nargs="*", default=None, help="subset of turns to run")
    args = ap.parse_args(argv)

    exec_key = os.environ.get("AGENT_EXEC_API_KEY")
    if not exec_key:
        print("AGENT_EXEC_API_KEY is not set", file=sys.stderr)
        return 2
    marker = args.marker or f"LOBEMK{uuid.uuid4().hex[:8].upper()}"
    lh = LobeHub(args.base_url, exec_key)
    user_id = lh.sign_up(f"e2e-{uuid.uuid4().hex[:10]}@example.test", f"E2e-{uuid.uuid4().hex}", "E2E Tester")
    agent = lh.inbox_agent()
    agent_id = agent["id"]
    lh.add_mcp_connector("ordertools", args.mcp_url)
    # The agent description is user-written text that LobeHub exports on invoke_agent spans; the
    # marker in it lets the privacy scan prove the collector removes it by default.
    lh.configure_agent(agent_id, model=args.model, provider=args.provider,
                       description=f"Order helper for tests {marker}-DESC",
                       plugins=[{"identifier": "ordertools", "mode": "pinned"}])

    runs = []
    ok = True
    for name, prompt, model in turns(marker):
        if args.only and name not in args.only:
            continue
        if model == "bad":
            lh.configure_agent(agent_id, model=args.bad_model, provider=args.provider)
        started = lh.exec_agent(user_id, agent_id, prompt)
        status = lh.wait(started["operationId"])
        if model == "bad":
            lh.configure_agent(agent_id, model=args.model, provider=args.provider)
        ok = ok and status in TERMINAL
        runs.append({"turn": name, "operation_id": started["operationId"],
                     "topic_id": started.get("topicId"), "status": status})
    print(json.dumps({"user_id": user_id, "agent_id": agent_id, "marker": marker, "runs": runs}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
