#!/usr/bin/env python3
"""Trace calls to the Vercel AI Gateway with traceAI-openai.

This is the recipe from docs/integrations/gateways/vercel-ai-gateway, plus four
small scenarios so it can be run end to end:

  chat    one non-streaming Chat Completions call
  stream  one streaming call
  tools   a tool round trip: model asks for a tool, the app runs it, the model answers
  error   a call with a wrong gateway key (the failure case)

The integration is only these lines (everything else is demo scaffolding):

    trace_provider = register(project_type=ProjectType.OBSERVE, project_name=...)
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)
    client = OpenAI(base_url="https://ai-gateway.vercel.sh/v1", api_key=<gateway key>)

Environment
  AI_GATEWAY_API_KEY   Vercel AI Gateway API key. Goes to the OpenAI client only.
  AI_GATEWAY_MODEL     A model id copied from Vercel's model list (provider/model).
  AI_GATEWAY_BASE_URL  Override of https://ai-gateway.vercel.sh/v1. Use it only to
                       point at a local stand-in; a real setup leaves it unset.
  FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI. Go to the tracer only.
  FI_PROJECT_NAME      Observe project (default: vercel-ai-gateway).
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

DEFAULT_BASE_URL = "https://ai-gateway.vercel.sh/v1"

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


def run_chat(client, model, prompt, system):
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    reply = client.chat.completions.create(model=model, messages=messages)
    return reply.choices[0].message.content


def run_stream(client, model, prompt, system):
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    stream = client.chat.completions.create(model=model, messages=messages, stream=True)
    return "".join(part.choices[0].delta.content or "" for part in stream if part.choices)


def run_tools(client, model, prompt, system, tracer):
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
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
        {"role": "assistant", "content": message.content, "tool_calls": [c.model_dump() for c in message.tool_calls]},
        {"role": "tool", "tool_call_id": call.id, "content": result},
    ]
    final = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
    return final.choices[0].message.content


def run_error(base_url, model, prompt):
    """A deliberately wrong gateway key: the gateway answers 401 and the span is ERROR."""
    bad = OpenAI(base_url=base_url, api_key="not-a-real-gateway-key")
    try:
        bad.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    except openai.APIStatusError as exc:
        return f"HTTP {exc.status_code}"
    return "no error (unexpected)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", choices=["all", "chat", "stream", "tools", "error"], default="all")
    ap.add_argument("--prompt", default="Say hello to the Vercel AI Gateway in five words.")
    ap.add_argument("--system", default="")
    ap.add_argument("--session-id", default=None)
    a = ap.parse_args(argv)

    api_key = os.environ.get("AI_GATEWAY_API_KEY")
    model = os.environ.get("AI_GATEWAY_MODEL")
    if not api_key or not model:
        print("set AI_GATEWAY_API_KEY and AI_GATEWAY_MODEL (a model id from Vercel's model list)", file=sys.stderr)
        return 2
    base_url = os.environ.get("AI_GATEWAY_BASE_URL", DEFAULT_BASE_URL)

    # 1. Future AGI tracing. The Future AGI key pair is read from FI_API_KEY / FI_SECRET_KEY.
    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=os.environ.get("FI_PROJECT_NAME", "vercel-ai-gateway"),
    )
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)

    # 2. The OpenAI client, pointed at the gateway. The key is the Vercel AI Gateway key.
    client = OpenAI(base_url=base_url, api_key=api_key)

    tracer = FITracer(trace_provider.get_tracer("vercel-ai-gateway-example"), config=TraceConfig())
    session_id = a.session_id or f"vercel-ai-gateway-{uuid.uuid4()}"
    wanted = ["chat", "stream", "tools", "error"] if a.scenario == "all" else [a.scenario]
    trace_id = None
    # Optional app-level parent span and session, so the calls are grouped in Observe.
    with using_session(session_id), tracer.start_as_current_span(
        "vercel-ai-gateway-demo", fi_span_kind=FiSpanKindValues.AGENT
    ) as root:
        ctx = root.get_span_context()
        trace_id = str(uuid.UUID(int=ctx.trace_id))
        for name in wanted:
            if name == "chat":
                out = run_chat(client, model, a.prompt, a.system)
            elif name == "stream":
                out = run_stream(client, model, a.prompt, a.system)
            elif name == "tools":
                out = run_tools(client, model, a.prompt, a.system, tracer)
            else:
                out = run_error(base_url, model, a.prompt)
            print(f"RESULT {name}: {out}")
    trace_provider.force_flush()
    trace_provider.shutdown()
    print(f"trace_id={trace_id}")
    print(f"session_id={session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
