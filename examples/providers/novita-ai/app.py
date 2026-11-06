#!/usr/bin/env python3
"""Trace Novita AI chat completions with traceAI-openai.

This is the recipe from docs/integrations/providers/novita-ai, plus a few small
scenarios so it can be run end to end:

  chat       one non-streaming chat completion
  stream     one streaming call (asks for the usage chunk Novita documents)
  tools      a tool round trip: model asks for a tool, the app runs it, the model answers
  error      a call with a wrong API key (failure case: Novita answers 401 FAILED_TO_AUTH)
  bad-model  a call with a model id that does not exist (failure case: 404 MODEL_NOT_FOUND)

The integration is only these lines (everything else is demo scaffolding):

    trace_provider = register(project_type=ProjectType.OBSERVE, project_name=...)
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)
    client = OpenAI(api_key=<NOVITA_API_KEY>, base_url="https://api.novita.ai/openai/v1")

Environment
  NOVITA_API_KEY     Novita API key. Goes to the OpenAI client only.
  NOVITA_MODEL       A model id copied from Novita's Model Hub. Not frozen here.
  NOVITA_TOOLS_MODEL Model id for the tools scenario only (default: NOVITA_MODEL). Novita answers
                     400 "model features function calling not support" for a model without
                     function calling, so pick one whose Model Hub entry lists it.
  NOVITA_BAD_MODEL   Model id for the bad-model scenario (default: a made-up id).
  NOVITA_BASE_URL    Override of https://api.novita.ai/openai/v1: the other form Novita shows
                     (https://api.novita.ai/openai), a local stand-in, or another
                     OpenAI-compatible server. A real setup leaves it unset.
  NOVITA_MAX_TOKENS  max_tokens sent on every call (default 128). Novita's reference lists
                     max_tokens as a required field; the live API accepted a call without it on
                     2026-10-18. Set it to 0 to omit it.
  FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI. Go to the tracer only.
  FI_PROJECT_NAME    Observe project (default: novita-ai).
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

# The base URL the recipe uses. Novita's quickstart and LLM API guide curl against
# https://api.novita.ai/openai/v1/chat/completions, so this is the base URL under which the
# OpenAI client builds exactly that request URL. Novita's API overview and several SDK
# guides also show https://api.novita.ai/openai; the live API answered on both on 2026-10-18.
NOVITA_BASE_URL = "https://api.novita.ai/openai/v1"

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


# Not a Novita model id. The bad-model scenario sends it to show what an unknown id looks like.
BAD_MODEL = "novita-ai-example/no-such-model"


def lookup_record(query):
    return f"record for {query}"


def resolve_base_url(env=None):
    env = os.environ if env is None else env
    return env.get("NOVITA_BASE_URL") or NOVITA_BASE_URL


def _messages(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def _limit(max_tokens):
    return {"max_tokens": max_tokens} if max_tokens else {}


def run_chat(client, model, prompt, system, max_tokens):
    reply = client.chat.completions.create(model=model, messages=_messages(prompt, system), **_limit(max_tokens))
    return reply.choices[0].message.content


def run_stream(client, model, prompt, system, max_tokens, include_usage=True):
    extra = {"stream_options": {"include_usage": True}} if include_usage else {}  # documented on Novita's chat reference
    stream = client.chat.completions.create(
        model=model, messages=_messages(prompt, system), stream=True, **_limit(max_tokens), **extra
    )
    # The usage chunk has an empty `choices` array, so check before indexing.
    return "".join(part.choices[0].delta.content or "" for part in stream if part.choices)


def run_tools(client, model, prompt, system, max_tokens, tracer):
    messages = _messages(prompt, system)
    first = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        **_limit(max_tokens),
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
    # Novita's function-calling guide says not to pass `tools` on this second request.
    final = client.chat.completions.create(model=model, messages=messages, **_limit(max_tokens))
    return final.choices[0].message.content


def run_error(base_url, model, prompt, max_tokens):
    """A deliberately wrong API key: the server answers with an HTTP error and the span is ERROR."""
    bad = OpenAI(api_key="not-a-real-novita-key", base_url=base_url)
    try:
        bad.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], **_limit(max_tokens))
    except openai.APIStatusError as exc:
        return f"HTTP {exc.status_code}"
    return "no error (unexpected)"


def run_bad_model(client, bad_model, prompt, max_tokens):
    """The right key and a model id that does not exist: Novita answers 404 MODEL_NOT_FOUND."""
    try:
        client.chat.completions.create(model=bad_model, messages=[{"role": "user", "content": prompt}], **_limit(max_tokens))
    except openai.APIStatusError as exc:
        return f"HTTP {exc.status_code}"
    return "no error (unexpected)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", choices=["all", "chat", "stream", "tools", "error", "bad-model"], default="all")
    ap.add_argument("--prompt", default="Say hello to Novita in five words.")
    ap.add_argument("--system", default="")
    ap.add_argument("--no-stream-usage", action="store_true", help="stream without stream_options.include_usage (the span then has no token counts)")
    ap.add_argument("--session-id", default=None)
    a = ap.parse_args(argv)

    api_key = os.environ.get("NOVITA_API_KEY")
    model = os.environ.get("NOVITA_MODEL")
    if not api_key or not model:
        print("set NOVITA_API_KEY and NOVITA_MODEL (a model id copied from Novita's Model Hub)", file=sys.stderr)
        return 2
    base_url = resolve_base_url()
    max_tokens = int(os.environ.get("NOVITA_MAX_TOKENS", "128"))
    tools_model = os.environ.get("NOVITA_TOOLS_MODEL") or model
    bad_model = os.environ.get("NOVITA_BAD_MODEL") or BAD_MODEL

    # 1. Future AGI tracing. The Future AGI key pair is read from FI_API_KEY / FI_SECRET_KEY.
    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=os.environ.get("FI_PROJECT_NAME", "novita-ai"),
    )
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)

    # 2. The OpenAI client, pointed at Novita.
    client = OpenAI(api_key=api_key, base_url=base_url)

    tracer = FITracer(trace_provider.get_tracer("novita-ai-example"), config=TraceConfig())
    session_id = a.session_id or f"novita-ai-{uuid.uuid4()}"
    wanted = ["chat", "stream", "tools", "error", "bad-model"] if a.scenario == "all" else [a.scenario]
    # Optional app-level parent span and session, so the calls are grouped in Observe.
    with using_session(session_id), tracer.start_as_current_span(
        "novita-ai-demo", fi_span_kind=FiSpanKindValues.AGENT
    ) as root:
        trace_id = str(uuid.UUID(int=root.get_span_context().trace_id))
        for name in wanted:
            try:
                if name == "chat":
                    out = run_chat(client, model, a.prompt, a.system, max_tokens)
                elif name == "stream":
                    out = run_stream(client, model, a.prompt, a.system, max_tokens, include_usage=not a.no_stream_usage)
                elif name == "tools":
                    out = run_tools(client, tools_model, a.prompt, a.system, max_tokens, tracer)
                elif name == "error":
                    out = run_error(base_url, model, a.prompt, max_tokens)
                else:
                    out = run_bad_model(client, bad_model, a.prompt, max_tokens)
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
