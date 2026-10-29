"""A Restate weather agent whose model and tool spans join the Restate invocation trace.

    python agent_service.py      # serves the Restate endpoint on 127.0.0.1:$SERVICE_PORT (default 9080)

Environment:
    FI_API_KEY, FI_SECRET_KEY   Future AGI keys (sent as X-Api-Key / X-Secret-Key)
    FI_BASE_URL                 where traceAI sends spans: the collector, e.g. http://localhost:4318
    FI_PROJECT_NAME             Observe project
    OPENAI_API_KEY              model provider key; OPENAI_BASE_URL for an OpenAI-compatible endpoint
    MODEL                       model id (default gpt-4.1-mini)
    FI_HIDE_INPUTS, FI_HIDE_OUTPUTS, FI_HIDE_INPUT_MESSAGES, FI_HIDE_OUTPUT_MESSAGES,
    FI_HIDE_LLM_INVOCATION_PARAMETERS
                                "true" keeps prompts, responses, tool arguments/results and model
                                request parameters out of spans
"""
import asyncio
import json
import os
import signal

import hypercorn.asyncio
import hypercorn.config
import restate
from fi_instrumentation import FITracer, TraceConfig, register, using_session
from fi_instrumentation.fi_types import ProjectType
from openai import AsyncOpenAI
from opentelemetry.trace import Status, StatusCode
from restate.exceptions import TerminalError
from restate.ext.tracing import RestateTracerProvider
from traceai_openai import OpenAIInstrumentor

# 1. A Future AGI tracer provider. Not registered globally: only the Restate-aware wrapper below uses it.
tracer_provider = register(
    project_name=os.environ.get("FI_PROJECT_NAME", "restate-agent"),
    project_type=ProjectType.OBSERVE,
    set_global_tracer_provider=False,
    verbose=False,
)
# 2. Every span created through this wrapper becomes a child of the Restate invocation attempt
#    that is running, and no span is created while Restate replays already-journaled steps.
restate_tracer_provider = RestateTracerProvider(tracer_provider)
OpenAIInstrumentor().instrument(tracer_provider=restate_tracer_provider)
tracer = FITracer(restate_tracer_provider.get_tracer(__name__), config=TraceConfig())

# Restate retries failed steps itself, so the OpenAI client should not retry on its own.
client = AsyncOpenAI(max_retries=0)
MODEL = os.environ.get("MODEL", "gpt-4.1-mini")

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get today's weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}

_failed_once: set[str] = set()  # invocations whose weather lookup already failed once (retry demo)


async def chat(model: str, messages: list, with_tools: bool) -> dict:
    """One model call. Runs inside ctx.run, so a completed call is journaled and never repeated."""
    kwargs = {"tools": [WEATHER_TOOL], "tool_choice": "required"} if with_tools else {}
    resp = await client.chat.completions.create(model=model, messages=messages, **kwargs)
    msg = resp.choices[0].message
    return {
        "role": "assistant",
        "content": msg.content,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in (msg.tool_calls or [])
        ],
    }


async def get_weather(invocation_id: str, arguments: str, flaky: bool) -> str:
    """The tool. With flaky=True the first lookup of an invocation fails, so Restate retries it."""
    args = json.loads(arguments or "{}")
    # record_exception=False: an exception event would carry a stack trace (local paths).
    with tracer.start_as_current_span(
        "get_weather", fi_span_kind="tool", record_exception=False, set_status_on_exception=False
    ) as span:
        span.set_tool(
            name="get_weather",
            description=WEATHER_TOOL["function"]["description"],
            parameters=WEATHER_TOOL["function"]["parameters"],
        )
        span.set_input(json.dumps(args))
        try:
            if flaky and invocation_id not in _failed_once:
                _failed_once.add(invocation_id)
                raise TimeoutError(f"weather backend timed out for {args.get('city')}")
            result = f"{args.get('city', 'unknown')}: 21C and sunny"
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))  # the type, not the message
            raise
        span.set_output(result)
        return result


agent = restate.VirtualObject("WeatherAgent")  # keyed by user: one conversation per user at a time


@agent.handler()
async def ask(ctx: restate.ObjectContext, req: dict) -> dict:
    invocation_id = ctx.request().id
    model = req.get("model", MODEL)
    messages = [
        {"role": "system", "content": "Use the get_weather tool, then answer in one sentence."},
        {"role": "user", "content": req["question"]},
    ]
    # No application session id? Use the Restate invocation id, so one invocation is one session.
    with using_session(req.get("session_id") or invocation_id):
        try:
            plan = await ctx.run_typed(
                "llm-plan", chat, restate.RunOptions(max_attempts=2), model=model, messages=messages, with_tools=True
            )
        except TerminalError:
            raise TerminalError("the model call failed")
        messages.append(plan)
        for call in plan["tool_calls"]:
            result = await ctx.run_typed(
                "tool-get_weather",
                get_weather,
                invocation_id=invocation_id,
                arguments=call["function"]["arguments"],
                flaky=bool(req.get("flaky")),
            )
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        final = await ctx.run_typed("llm-answer", chat, model=model, messages=messages, with_tools=False)
    return {"answer": final["content"]}


app = restate.app(services=[agent])


async def _let_sdk_install_sigterm_handler() -> None:
    """Call the app once, as hypercorn's startup does. restate-sdk 1.0.5 installs its SIGTERM handler then."""

    async def receive() -> dict:
        return {"type": "lifespan.startup"}

    async def send(_message: dict) -> None:
        pass

    try:
        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
    except Exception:
        pass  # the SDK has no lifespan support and says so by raising


async def serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    # restate-sdk 1.0.5 adds its own asyncio SIGTERM handler the first time the app is called. It tells
    # running invocations to wind down, but it replaces the server's handler, so SIGTERM alone would
    # never stop the server or flush spans. Let the SDK install it first, then add a Python-level
    # handler on top: asyncio still runs the SDK's handler, and this one stops the server.
    await _let_sdk_install_sigterm_handler()
    signal.signal(signal.SIGTERM, lambda *_: loop.call_soon_threadsafe(stop.set))
    loop.add_signal_handler(signal.SIGINT, stop.set)
    config = hypercorn.config.Config()
    config.bind = [f"127.0.0.1:{os.environ.get('SERVICE_PORT', '9080')}"]
    await hypercorn.asyncio.serve(app, config, shutdown_trigger=stop.wait)


if __name__ == "__main__":
    asyncio.run(serve())
    tracer_provider.shutdown()  # flush spans still buffered when SIGTERM arrives
