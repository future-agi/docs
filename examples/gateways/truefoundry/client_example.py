#!/usr/bin/env python3
"""Trace OpenAI-client calls to the TrueFoundry AI Gateway with traceai-openai.

This is the client-tracing path from the TrueFoundry page: the Future AGI
instrumentor wraps the OpenAI client, and the client's base URL points at the
gateway. TrueFoundry never sees your Future AGI keys.

Environment:
  FI_API_KEY, FI_SECRET_KEY   Future AGI keys (read by register())
  FI_BASE_URL                 self-hosted Future AGI only; the SDK appends /tracer/v1/traces
  FI_PROJECT_NAME             Observe project name (default: truefoundry-gateway)
  TFY_BASE_URL                gateway base URL (default: https://gateway.truefoundry.ai, TrueFoundry SaaS)
  TFY_API_KEY                 TrueFoundry Personal Access Token or Virtual Account Token
  TFY_MODEL                   gateway model id, `provider_account/model_name`
                              (default: openai-main/gpt-4o-mini)

Content capture is on by default in traceai-openai. To keep prompts, responses,
and tool arguments or results out of Future AGI, set the documented switches
before running, for example:
  FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_INPUT_MESSAGES=true FI_HIDE_OUTPUT_MESSAGES=true
  FI_HIDE_LLM_INVOCATION_PARAMETERS=true FI_HIDE_ERROR_DETAILS=true
"""
import json
import os
import sys
from typing import Callable, Optional

from fi_instrumentation import FITracer, TraceConfig, register
from fi_instrumentation.fi_types import ProjectType
from openai import OpenAI
from traceai_openai import OpenAIInstrumentor

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Look up the shipping status of an order.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    }
]


def lookup_order(order_id: str) -> str:
    return json.dumps({"order_id": order_id, "status": "shipped", "carrier": "UPS"})


def run_agent(
    client: OpenAI,
    tracer: FITracer,
    model: str,
    prompt: str,
    lookup: Callable[[str], str] = lookup_order,
) -> str:
    """One agent turn: LLM call, tool call, LLM call."""
    tool = tracer.tool(lookup, name="get_order_status")

    @tracer.agent(name="order-assistant")
    def agent(user_prompt: str) -> str:
        messages = [{"role": "user", "content": user_prompt}]
        first = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        choice = first.choices[0].message
        if not choice.tool_calls:
            return choice.content or ""
        messages.append(choice.model_dump(exclude_none=True))
        for call in choice.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": tool(args.get("order_id", ""))}
            )
        final = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        return final.choices[0].message.content or ""

    return agent(prompt)


def run_stream(client: OpenAI, model: str, prompt: str) -> str:
    """Return a complete answer, closing the stream on success or failure."""
    parts = []
    finish_reason = None
    with client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        stream_options={"include_usage": True},
    ) as stream:
        for chunk in stream:
            for choice in chunk.choices:
                if choice.index != 0:
                    continue
                if choice.delta.content:
                    parts.append(choice.delta.content)
                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason
        # EOF and [DONE] alone do not prove the model finished its answer.
        # Token limits and content filtering also produce partial answers.
        if finish_reason != "stop":
            raise RuntimeError("The gateway did not return a complete answer")
    return "".join(parts)


def build(project_name: Optional[str] = None):
    trace_provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=project_name or os.environ.get("FI_PROJECT_NAME", "truefoundry-gateway"),
        verbose=False,
    )
    config = TraceConfig()
    OpenAIInstrumentor().instrument(tracer_provider=trace_provider, config=config)
    client = OpenAI(
        base_url=os.environ.get("TFY_BASE_URL", "https://gateway.truefoundry.ai"),
        api_key=os.environ["TFY_API_KEY"],
    )
    tracer = FITracer(trace_provider.get_tracer("truefoundry-example"), config=config)
    return trace_provider, client, tracer


def main(argv: list) -> int:
    model = os.environ.get("TFY_MODEL", "openai-main/gpt-4o-mini")
    stream = "--stream" in argv
    argv = [a for a in argv if a != "--stream"]
    prompt = " ".join(argv[1:]) or "What is the shipping status of order A-1042? Use the tool."
    trace_provider, client, tracer = build()
    code = 0
    try:
        print(run_stream(client, model, prompt) if stream else run_agent(client, tracer, model, prompt))
    except Exception as exc:
        print(f"gateway call failed: {type(exc).__name__}", file=sys.stderr)
        code = 1
    finally:
        trace_provider.force_flush()
        trace_provider.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
