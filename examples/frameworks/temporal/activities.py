"""Activities: every model call and every tool call runs here, never in workflow code."""
import json

from fi_instrumentation import FITracer, TraceConfig
from openai import AsyncOpenAI
from opentelemetry import trace
from temporalio import activity

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get today's weather for a city.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    },
}

# OPENAI_API_KEY and OPENAI_BASE_URL select the model provider. Temporal retries failed activities
# itself, so the OpenAI client does not retry on its own.
client = AsyncOpenAI(max_retries=0)


def _tracer() -> FITracer:
    # The global provider is the replay-safe one that setup_tracing() registered.
    return FITracer(trace.get_tracer(__name__), config=TraceConfig())


async def _chat(model: str, messages: list[dict], with_tools: bool) -> dict:
    kwargs = {"tools": [WEATHER_TOOL], "tool_choice": "required"} if with_tools else {}
    response = await client.chat.completions.create(model=model, messages=messages, **kwargs)
    message = response.choices[0].message
    return {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in (message.tool_calls or [])
        ],
    }


@activity.defn
async def llm_plan(model: str, messages: list[dict]) -> dict:
    return await _chat(model, messages, with_tools=True)


@activity.defn
async def llm_answer(model: str, messages: list[dict]) -> dict:
    return await _chat(model, messages, with_tools=False)


@activity.defn
async def get_weather(arguments: str, flaky: bool) -> str:
    """The tool. With flaky=True the first attempt fails, so Temporal retries the activity."""
    args = json.loads(arguments or "{}")
    with _tracer().start_as_current_span("get_weather", fi_span_kind="tool") as span:
        span.set_tool(
            name="get_weather",
            description=WEATHER_TOOL["function"]["description"],
            parameters=WEATHER_TOOL["function"]["parameters"],
        )
        span.set_input(json.dumps(args))
        if flaky and activity.info().attempt == 1:
            raise TimeoutError(f"weather backend timed out for {args.get('city')}")
        result = f"{args.get('city', 'unknown')}: 21C and sunny"
        span.set_output(result)
        return result
