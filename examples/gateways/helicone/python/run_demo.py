#!/usr/bin/env python3
"""Run a small agent against Helicone (or a local stand-in) and trace it in Future AGI.

Configuration comes from the environment:

  FI_API_KEY, FI_SECRET_KEY   Future AGI keys (read by register())
  FI_BASE_URL                 Future AGI collector origin, for a self-hosted Future AGI
  HELICONE_SURFACE            gateway (default) or proxy
  HELICONE_BASE_URL           defaults to the hosted URL of the surface
  HELICONE_API_KEY            Helicone key
  OPENAI_API_KEY              only for the classic proxy
  HELICONE_MODEL              model name, e.g. openai/gpt-4o-mini on the AI Gateway

Scenarios: agent (two chat calls and a tool, under an agent span), stream, error
(a call that fails), auth-error (a call with a wrong key; only meaningful where the endpoint
checks the key), core (agent + stream + error), all.
The last stdout line is a JSON summary. Secrets are never printed.
Trace ids are not printed; look them up in Future AGI (project = --project).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fi_instrumentation import FITracer, using_session, using_user  # noqa: E402
from openai import OpenAIError  # noqa: E402

from helicone_tracing import env_client, make_client, setup_tracing  # noqa: E402


def helicone_headers(session_id: str, user_id: str, path: str):
    """Helicone's own session / user / property headers. Helicone reads these; Future AGI does not."""
    return {
        "Helicone-Session-Id": session_id,
        "Helicone-Session-Path": path,
        "Helicone-Session-Name": "weather-demo",
        "Helicone-User-Id": user_id,
        "Helicone-Property-Environment": "e2e",
    }


def build_tools(tool_marker: str):
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": f"Get the current weather for a city. Internal ref {tool_marker}.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "case_ref": {"type": "string", "description": "Copy the 'Case ref' value from the system message."},
                    },
                    "required": ["city", "case_ref"],
                },
            },
        }
    ]


def run_agent(provider, client, model, marker, fi_session_id, fi_user_id, helicone_ids):
    """helicone_ids is None (send no Helicone headers) or (session_id, user_id)."""
    tracer = FITracer(provider.get_tracer("helicone-demo"))

    @tracer.tool(name="get_weather", description="Look up the weather for a city")
    def get_weather(city: str, case_ref: str = "") -> str:
        return f"21C and sunny in {city} (case {case_ref})" if case_ref else f"21C and sunny in {city}"

    @tracer.agent(name="weather-agent")
    def agent(question: str) -> str:
        tools = build_tools(marker.replace("HELI-MARK", "HELI-TOOLDEF"))
        messages = [
            {"role": "system", "content": f"You are a weather assistant. Case ref {marker}."},
            {"role": "user", "content": question},
        ]
        hdr = (lambda p: {"extra_headers": helicone_headers(*helicone_ids, p)}) if helicone_ids else (lambda p: {})
        first = client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice="required", **hdr("/agent/plan")
        )
        msg = first.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls or []:
            args = json.loads(call.function.arguments)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": get_weather(**args)})
        final = client.chat.completions.create(model=model, messages=messages, tools=tools, **hdr("/agent/answer"))
        return final.choices[0].message.content or ""

    question = f"What is the weather in Paris? Include the reference {marker} in your answer. My email is jane.doe@example.com."
    if fi_session_id is None:  # no Future AGI session: shows Helicone's headers do not create one
        return agent(question)
    with using_session(fi_session_id), using_user(fi_user_id):
        return agent(question)


def run_stream(provider, client, model, marker, include_usage):
    tracer = FITracer(provider.get_tracer("helicone-demo"))
    kwargs = {"stream_options": {"include_usage": True}} if include_usage else {}
    with tracer.start_as_current_span("stream-demo", fi_span_kind="chain"):
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"Count from 1 to 3, then say {marker}."}],
            stream=True,
            **kwargs,
        )
        return "".join(c.choices[0].delta.content or "" for c in stream if c.choices)


def run_error(client, model, marker):
    try:
        client.chat.completions.create(model=model, messages=[{"role": "user", "content": f"hello {marker}"}])
    except OpenAIError as exc:
        return type(exc).__name__
    return "no-error"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="all", choices=["agent", "stream", "error", "auth-error", "core", "all"])
    ap.add_argument("--project", default=os.environ.get("FI_PROJECT_NAME", "helicone-demo"))
    ap.add_argument("--model", default=os.environ.get("HELICONE_MODEL", "openai/gpt-4o-mini"))
    ap.add_argument("--error-model", default="force-500")
    ap.add_argument("--marker", default="HELI-MARK-demo")
    ap.add_argument("--session-id", default=str(uuid.uuid4()), help="Future AGI session id (using_session)")
    ap.add_argument("--user-id", default="demo-user-1", help="Future AGI user id (using_user)")
    ap.add_argument("--no-fi-session", action="store_true", help="do not call using_session / using_user")
    ap.add_argument("--helicone-session-id", default=str(uuid.uuid4()), help="value of the Helicone-Session-Id header")
    ap.add_argument("--helicone-user-id", default="helicone-user-1", help="value of the Helicone-User-Id header")
    ap.add_argument("--no-helicone-headers", action="store_true")
    ap.add_argument("--no-stream-usage", action="store_true")
    ap.add_argument("--scrub-errors", action="store_true", help="wrap the exporter with RedactErrorDetailsExporter")
    args = ap.parse_args(argv)

    provider = setup_tracing(args.project, scrub_error_details=args.scrub_errors)
    surface = os.environ.get("HELICONE_SURFACE", "gateway")
    # max_retries=0: one failed call is one ERROR span, not three.
    client = env_client(surface, max_retries=0)
    summary = {"surface": surface, "base_url": str(client.base_url), "project": args.project, "scenarios": {}}

    def traced(name, fn):
        summary["scenarios"][name] = fn()

    want = lambda s: args.scenario in (s, "all") or (args.scenario == "core" and s != "auth-error")
    if want("agent"):
        traced(
            "agent",
            lambda: bool(
                run_agent(
                    provider,
                    client,
                    args.model,
                    args.marker,
                    None if args.no_fi_session else args.session_id,
                    args.user_id,
                    None if args.no_helicone_headers else (args.helicone_session_id, args.helicone_user_id),
                )
            ),
        )
    if want("stream"):
        traced("stream", lambda: bool(run_stream(provider, client, args.model, args.marker, not args.no_stream_usage)))
    if want("error"):
        traced("error", lambda: run_error(client, args.error_model, args.marker))
    if want("auth-error"):
        bad = make_client(
            surface,
            helicone_key="wrong-helicone-key",
            provider_key="wrong-provider-key" if surface == "proxy" else None,
            base_url=os.environ.get("HELICONE_BASE_URL"),
            max_retries=0,
        )
        traced("auth-error", lambda: run_error(bad, args.model, args.marker))

    provider.force_flush()
    provider.shutdown()
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
