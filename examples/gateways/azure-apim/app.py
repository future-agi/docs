#!/usr/bin/env python3
"""Variant A client: an app that holds NO Future AGI keys and exports its traces through an APIM egress API.

The integration is the register() call below (everything else is demo scaffolding so a run produces an agent
span, LLM spans, a tool span and one failing call):

    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name="my-chatbot",
        headers={"Ocp-Apim-Subscription-Key": os.environ["APIM_SUBSCRIPTION_KEY"]},   # APIM's key, not Future AGI's
    )                                       # FI_BASE_URL = https://<your-apim>.azure-api.net
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)

Environment
  FI_BASE_URL            APIM host only, e.g. https://contoso.azure-api.net . register() always appends
                         /tracer/v1/traces and drops any path you put here, so the APIM API suffix must be `tracer`.
  FI_PROJECT_NAME        Observe project (default azure-apim-egress)
  APIM_SUBSCRIPTION_KEY  sent as Ocp-Apim-Subscription-Key (optional when the API does not require a subscription)
  FI_API_KEY/FI_SECRET_KEY  deliberately NOT used. The app aborts if they are set, to prove the gateway holds them.
  LLM_BASE_URL, LLM_API_KEY, LLM_MODEL   any OpenAI-compatible endpoint (an Azure OpenAI deployment behind APIM works)
  FI_HIDE_INPUTS, FI_HIDE_OUTPUTS        true keeps prompts and completions out of the spans (traceAI TraceConfig)
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

TOOLS = [{
    "type": "function",
    "function": {
        "name": "lookup_record",
        "description": "Look up a record by a free-text query.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}]


def msgs(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def run_tools(client, model, prompt, system, tracer):
    messages = msgs(prompt, system)
    first = client.chat.completions.create(
        model=model, messages=messages, tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "lookup_record"}},
    )
    message = first.choices[0].message
    if not message.tool_calls:
        return message.content
    call = message.tool_calls[0]
    with tracer.start_as_current_span("tool lookup_record", fi_span_kind=FiSpanKindValues.TOOL):
        result = f"record for {json.loads(call.function.arguments).get('query', '')}"
    messages += [
        {"role": "assistant", "content": message.content, "tool_calls": [c.model_dump() for c in message.tool_calls]},
        {"role": "tool", "tool_call_id": call.id, "content": result},
    ]
    return client.chat.completions.create(model=model, messages=messages, tools=TOOLS).choices[0].message.content


def run_error(base_url, model, prompt):
    """A deliberately wrong LLM key: the model endpoint answers 401 and the span is ERROR."""
    try:
        OpenAI(base_url=base_url, api_key="not-a-real-key").chat.completions.create(model=model, messages=msgs(prompt, ""))
    except openai.APIStatusError as exc:
        return f"HTTP {exc.status_code}"
    return "no error (unexpected)"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="Say hello from behind Azure API Management.")
    ap.add_argument("--system", default="")
    ap.add_argument("--scenario", choices=["all", "chat", "tools", "error"], default="all")
    a = ap.parse_args(argv)

    if os.environ.get("FI_API_KEY") or os.environ.get("FI_SECRET_KEY"):
        print("unset FI_API_KEY and FI_SECRET_KEY: in this variant only the APIM policy holds them", file=sys.stderr)
        return 2
    base, key, model = os.environ.get("LLM_BASE_URL"), os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
    if not (base and key and model and os.environ.get("FI_BASE_URL")):
        print("set FI_BASE_URL, LLM_BASE_URL, LLM_API_KEY and LLM_MODEL", file=sys.stderr)
        return 2

    sub = os.environ.get("APIM_SUBSCRIPTION_KEY")
    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=os.environ.get("FI_PROJECT_NAME", "azure-apim-egress"),
        headers={"Ocp-Apim-Subscription-Key": sub} if sub else None,
        verbose=False,
    )
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider)
    client = OpenAI(base_url=base, api_key=key)

    tracer = FITracer(trace_provider.get_tracer("azure-apim-example"), config=TraceConfig())
    session_id = f"azure-apim-{uuid.uuid4()}"
    wanted = ["chat", "tools", "error"] if a.scenario == "all" else [a.scenario]
    with using_session(session_id), tracer.start_as_current_span("azure-apim-demo", fi_span_kind=FiSpanKindValues.AGENT) as root:
        trace_id = str(uuid.UUID(int=root.get_span_context().trace_id))
        for name in wanted:
            if name == "chat":
                out = client.chat.completions.create(model=model, messages=msgs(a.prompt, a.system)).choices[0].message.content
            elif name == "tools":
                out = run_tools(client, model, a.prompt, a.system, tracer)
            else:
                out = run_error(base, model, a.prompt)
            print(f"RESULT {name}: {out}")
    trace_provider.force_flush()
    trace_provider.shutdown()
    print(f"trace_id={trace_id}")
    print(f"session_id={session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
