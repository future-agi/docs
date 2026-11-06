#!/usr/bin/env python3
"""Run agent.py once with a Client-mode tracer whose export goes to the collector.

IBM's documented external-agent setup builds TracerConfig(client=Client(...)). In that mode the
SDK sends an `Authorization: Bearer <watsonx token>` header and tenant/agent/workspace resource
attributes, and exports to <instance>/inject/traces, or to `trace_injection_path` when that is an
absolute URL. This script uses a local-mode Client with a placeholder JWT-shaped token (no IBM
call is made) and points trace_injection_path at the collector, to show that the collector never
forwards the bearer token and removes the user id taken from the token.

  client_mode_run.py --collector http://localhost:4318/v1/traces --token-file token.txt "question"

The token (and the user id inside it) are written by the caller; this script never prints them.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collector", required=True, help="collector URL, e.g. http://localhost:4318/v1/traces")
    ap.add_argument("--token-file", required=True, help="file holding the placeholder bearer token")
    ap.add_argument("question")
    a = ap.parse_args()
    os.environ.setdefault("WXO_OTLP_ENDPOINT", a.collector)  # agent.py's own tracer is replaced below

    from ibm_watsonx_orchestrate_sdk.client import Client
    from ibm_watsonx_orchestrate_sdk.observability import Tracer, TracerConfig, register_tracer

    import agent

    token = Path(a.token_file).read_text().strip()
    client = Client(api_key=token, instance_url="http://127.0.0.1:9", local=True)  # local mode: no token exchange
    tracer = Tracer(TracerConfig(
        service_name="weather-agent",
        client=client,
        agent_id="weather-agent-e2e",
        workspace_id="workspace-e2e",
        environment="draft",
        trace_injection_path=a.collector,  # absolute URL: used as-is instead of <instance>/inject/traces
    ))
    register_tracer(tracer)
    standalone, agent.tracer = agent.tracer, tracer
    try:
        print(agent.ask(a.question))
    finally:
        tracer.shutdown()
        standalone.shutdown()  # created at import, never used here
    return 0


if __name__ == "__main__":
    sys.exit(main())
