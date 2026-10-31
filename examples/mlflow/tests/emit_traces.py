"""Offline MLflow/autolog fixture. The provider transport never opens a socket."""
import httpx
import mlflow
from mlflow.entities import SpanEvent
from openai import OpenAI

PRIVATE = "PRIVATE-MLFLOW-CONTENT"


def completion(request):
    assert PRIVATE.encode() in request.content
    return httpx.Response(200, json={
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": PRIVATE,
        }}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
    })


mlflow.openai.autolog()
client = OpenAI(api_key="synthetic-not-a-credential", http_client=httpx.Client(
    transport=httpx.MockTransport(completion),
))

with mlflow.start_span(name=PRIVATE, span_type="CHAIN") as root:
    root.set_inputs({"query": PRIVATE})
    root.set_outputs({"answer": PRIVATE})
    root.set_attribute("customer.custom_field", PRIVATE)
    root.add_event(SpanEvent("checkpoint", attributes={"content": PRIVATE}))
    with mlflow.start_span(name=PRIVATE, span_type="TOOL") as tool:
        tool.set_inputs({"arguments": PRIVATE})
        tool.set_outputs({"result": PRIVATE})
        tool.add_event(SpanEvent("gen_ai.user.message", attributes={"body": PRIVATE}))
    client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": PRIVATE}],
        tools=[{"type": "function", "function": {"name": "refund", "description": PRIVATE,
                                                 "parameters": {"type": "object", "properties": {}}}}],
    )
    try:
        with mlflow.start_span(name=PRIVATE, span_type="TOOL"):
            raise ValueError(PRIVATE)
    except ValueError:
        pass

mlflow.flush_trace_async_logging()
client.close()
