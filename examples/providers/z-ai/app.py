#!/usr/bin/env python3
"""Trace Z.ai general-platform chat completions with traceAI-openai.

This is the recipe from docs/integrations/providers/z-ai, plus a few small
scenarios so it can be run end to end:

  chat      one non-streaming chat completion
  stream    one streaming call (Z.ai sends usage on the last chunk by itself)
  tools     a tool round trip: model asks for a tool, the app runs it, the model answers
  thinking  a call that passes Z.ai's `thinking` field through extra_body
  error     a call with a wrong API key (the failure case)

The integration is only these lines (everything else is demo scaffolding):

    trace_provider = register(project_type=ProjectType.OBSERVE, project_name=...)
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)
    client = OpenAI(api_key=<ZAI_API_KEY>, base_url="https://api.z.ai/api/paas/v4/")

Environment
  ZAI_API_KEY      Z.ai API key. Goes to the OpenAI client only.
  ZAI_MODEL        A current Z.ai model code. Not frozen here.
  ZAI_BASE_URL     Override of the base URL. Use it only to point at a local
                   stand-in; a real setup leaves it unset. The three Z.ai Coding
                   Plan URLs are refused (see docs: "Coding Plan is not this page").
  FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI. Go to the tracer only.
  FI_PROJECT_NAME  Observe project (default: z-ai).
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

# The one base URL this recipe supports: the general platform OpenAI-compatible endpoint,
# written exactly as Z.ai's OpenAI Python guide prints it (trailing slash included).
ZAI_BASE_URL = "https://api.z.ai/api/paas/v4/"

# Z.ai's GLM Coding Plan endpoints (docs.z.ai/devpack/quick-start). Different product, not this recipe.
CODING_PLAN_URLS = (
    "https://api.z.ai/api/anthropic",
    "https://api.z.ai/api/coding/paas/v4",
    "https://api.z.ai/api/v1",
)

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


def is_coding_plan_url(url):
    """True for the three Coding Plan base URLs, or anything under them (any case, trailing slash or not)."""
    normal = url.strip().rstrip("/").lower()
    return any(normal == u.rstrip("/").lower() or normal.startswith(u.rstrip("/").lower() + "/") for u in CODING_PLAN_URLS)


def resolve_base_url(env=None):
    """The base URL to use, or (None, message) when it must be refused."""
    env = os.environ if env is None else env
    base_url = env.get("ZAI_BASE_URL") or ZAI_BASE_URL
    if is_coding_plan_url(base_url):
        return None, (
            "refusing a Z.ai Coding Plan URL. The GLM Coding Plan is a different product with its own endpoints "
            "and is not covered by this recipe; use the general platform URL " + ZAI_BASE_URL
        )
    return base_url, None


def _messages(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def run_chat(client, model, prompt, system):
    reply = client.chat.completions.create(model=model, messages=_messages(prompt, system))
    return reply.choices[0].message.content


def run_stream(client, model, prompt, system):
    # Z.ai documents `usage` on the last chunk of a stream; the app does not ask for it.
    stream = client.chat.completions.create(model=model, messages=_messages(prompt, system), stream=True)
    return "".join(part.choices[0].delta.content or "" for part in stream if part.choices)


def run_thinking(client, model, prompt, system, mode="enabled"):
    # `thinking` is a Z.ai field the OpenAI SDK does not know; extra_body carries it.
    reply = client.chat.completions.create(
        model=model,
        messages=_messages(prompt, system),
        extra_body={"thinking": {"type": mode}},
    )
    return reply.choices[0].message.content


def run_tools(client, model, prompt, system, tracer):
    messages = _messages(prompt, system)
    first = client.chat.completions.create(model=model, messages=messages, tools=TOOLS, tool_choice="auto")
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
    """A deliberately wrong API key: Z.ai answers 401 and the span is ERROR."""
    bad = OpenAI(api_key="not-a-real-zai-key", base_url=base_url)
    try:
        bad.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    except openai.APIStatusError as exc:
        return f"HTTP {exc.status_code}"
    return "no error (unexpected)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", choices=["all", "chat", "stream", "tools", "thinking", "error"], default="all")
    ap.add_argument("--prompt", default="Say hello to Z.ai in five words.")
    ap.add_argument("--system", default="")
    ap.add_argument("--thinking", choices=["disabled", "enabled"], default="enabled", help="value for the thinking scenario")
    ap.add_argument("--session-id", default=None)
    a = ap.parse_args(argv)

    api_key = os.environ.get("ZAI_API_KEY")
    model = os.environ.get("ZAI_MODEL")
    if not api_key or not model:
        print("set ZAI_API_KEY and ZAI_MODEL (a current model code from Z.ai's model list)", file=sys.stderr)
        return 2
    base_url, problem = resolve_base_url()
    if problem:
        print(problem, file=sys.stderr)
        return 2

    # 1. Future AGI tracing. The Future AGI key pair is read from FI_API_KEY / FI_SECRET_KEY.
    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=os.environ.get("FI_PROJECT_NAME", "z-ai"),
    )
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)

    # 2. The OpenAI client, pointed at the Z.ai general platform endpoint.
    client = OpenAI(api_key=api_key, base_url=base_url)

    tracer = FITracer(trace_provider.get_tracer("z-ai-example"), config=TraceConfig())
    session_id = a.session_id or f"z-ai-{uuid.uuid4()}"
    wanted = ["chat", "stream", "tools", "thinking", "error"] if a.scenario == "all" else [a.scenario]
    # Optional app-level parent span and session, so the calls are grouped in Observe.
    with using_session(session_id), tracer.start_as_current_span(
        "z-ai-demo", fi_span_kind=FiSpanKindValues.AGENT
    ) as root:
        trace_id = str(uuid.UUID(int=root.get_span_context().trace_id))
        for name in wanted:
            try:
                if name == "chat":
                    out = run_chat(client, model, a.prompt, a.system)
                elif name == "stream":
                    out = run_stream(client, model, a.prompt, a.system)
                elif name == "tools":
                    out = run_tools(client, model, a.prompt, a.system, tracer)
                elif name == "thinking":
                    out = run_thinking(client, model, a.prompt, a.system, a.thinking)
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
