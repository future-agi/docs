#!/usr/bin/env python3
"""Trace CometAPI chat completions with traceAI-openai.

This is the recipe from docs/integrations/providers/cometapi, plus a few small
scenarios so it can be run end to end:

  chat      one non-streaming chat completion
  stream    one streaming call (asks for the usage chunk CometAPI documents)
  tools     a tool round trip: model asks for a tool, the app runs it, the model answers
  error     a call with a wrong API key (the failure case)

The integration is only these lines (everything else is demo scaffolding):

    trace_provider = register(project_type=ProjectType.OBSERVE, project_name=...)
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)
    client = OpenAI(api_key=<COMETAPI_KEY>, base_url="https://api.cometapi.com/v1")

Environment
  COMETAPI_KEY       CometAPI API key. Goes to the OpenAI client only.
  COMETAPI_MODEL     A current model ID from CometAPI's Models page. Not frozen here.
  COMETAPI_BASE_URL  Override of https://api.cometapi.com/v1. Use it only to point at a
                     local stand-in or another OpenAI-compatible server; a real setup
                     leaves it unset.
  FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI. Go to the tracer only.
  FI_PROJECT_NAME    Observe project (default: cometapi).
  FI_HIDE_INPUTS, FI_HIDE_OUTPUTS, FI_HIDE_LLM_INVOCATION_PARAMETERS
                     Set to true to keep prompts, completions and request
                     parameters out of the spans (traceAI TraceConfig).
"""
import argparse
import json
import os
import sys
import uuid

import openai
from fi_instrumentation import FITracer, TraceConfig, register, using_session
from fi_instrumentation.fi_types import FiSpanKindValues, ProjectType
from openai import OpenAI
from traceai_openai import OpenAIInstrumentor

# The one OpenAI-compatible base URL CometAPI documents (quickstart, "Base URL").
COMETAPI_BASE_URL = "https://api.cometapi.com/v1"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_record",
            "description": "Look up a record by a free-text query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]


def lookup_record(query):
    return f"record for {query}"


def resolve_base_url(env=None):
    env = os.environ if env is None else env
    return env.get("COMETAPI_BASE_URL") or COMETAPI_BASE_URL


def _messages(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def run_chat(client, model, prompt, system):
    reply = client.chat.completions.create(model=model, messages=_messages(prompt, system))
    return reply.choices[0].message.content


def run_stream(client, model, prompt, system, include_usage=True):
    extra = {"stream_options": {"include_usage": True}} if include_usage else {}  # documented on CometAPI's chat page
    stream = client.chat.completions.create(model=model, messages=_messages(prompt, system), stream=True, **extra)
    # CometAPI documents that chunks can have an empty `choices` array, so check before indexing.
    return "".join(part.choices[0].delta.content or "" for part in stream if part.choices)


def run_tools(client, model, prompt, system, tracer):
    messages = _messages(prompt, system)
    first = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "lookup_record"}},
    )
    message = first.choices[0].message
    if not message.tool_calls:
        return message.content
    call = message.tool_calls[0]
    # Your own spans carry only what you put on them. This one records no arguments.
    with tracer.start_as_current_span("tool lookup_record", fi_span_kind=FiSpanKindValues.TOOL):
        result = lookup_record(**json.loads(call.function.arguments))
    messages += [
        {"role": "assistant", "content": message.content or "", "tool_calls": [c.model_dump() for c in message.tool_calls]},
        {"role": "tool", "tool_call_id": call.id, "content": result},
    ]
    final = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
    return final.choices[0].message.content


def run_error(base_url, model, prompt):
    """A deliberately wrong API key: CometAPI answers 401 and the span is ERROR."""
    bad = OpenAI(api_key="not-a-real-cometapi-key", base_url=base_url)
    try:
        bad.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    except openai.APIStatusError as exc:
        return f"HTTP {exc.status_code}"
    return "no error (unexpected)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", choices=["all", "chat", "stream", "tools", "error"], default="all")
    ap.add_argument("--prompt", default="Say hello to CometAPI in five words.")
    ap.add_argument("--system", default="")
    ap.add_argument("--no-stream-usage", action="store_true", help="stream without stream_options.include_usage (the span then has no token counts)")
    ap.add_argument("--session-id", default=None)
    a = ap.parse_args(argv)

    api_key = os.environ.get("COMETAPI_KEY")
    model = os.environ.get("COMETAPI_MODEL")
    if not api_key or not model:
        print("set COMETAPI_KEY and COMETAPI_MODEL (a current model ID from CometAPI's Models page)", file=sys.stderr)
        return 2
    base_url = resolve_base_url()

    # 1. Future AGI tracing. The Future AGI key pair is read from FI_API_KEY / FI_SECRET_KEY.
    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=os.environ.get("FI_PROJECT_NAME", "cometapi"),
    )
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)

    # 2. The OpenAI client, pointed at CometAPI.
    client = OpenAI(api_key=api_key, base_url=base_url)

    tracer = FITracer(trace_provider.get_tracer("cometapi-example"), config=TraceConfig())
    session_id = a.session_id or f"cometapi-{uuid.uuid4()}"
    wanted = ["chat", "stream", "tools", "error"] if a.scenario == "all" else [a.scenario]
    # Optional app-level parent span and session, so the calls are grouped in Observe.
    with using_session(session_id), tracer.start_as_current_span(
        "cometapi-demo", fi_span_kind=FiSpanKindValues.AGENT
    ) as root:
        trace_id = str(uuid.UUID(int=root.get_span_context().trace_id))
        for name in wanted:
            try:
                if name == "chat":
                    out = run_chat(client, model, a.prompt, a.system)
                elif name == "stream":
                    out = run_stream(client, model, a.prompt, a.system, include_usage=not a.no_stream_usage)
                elif name == "tools":
                    out = run_tools(client, model, a.prompt, a.system, tracer)
                else:
                    out = run_error(base_url, model, a.prompt)
            except openai.OpenAIError as exc:  # keep the demo going; the span already records the failure
                out = f"{type(exc).__name__}"
            print(f"RESULT {name}: {out}")
    trace_provider.force_flush()
    trace_provider.shutdown()
    print(f"base_url={base_url}")
    print(f"trace_id={trace_id}")
    print(f"session_id={session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
