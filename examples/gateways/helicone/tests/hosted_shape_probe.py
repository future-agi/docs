"""Build the OpenAI client the way the docs page does, for Helicone's hosted base URLs, and
send one chat call through an in-process httpx transport. No network is used: this only shows
which URL, path and headers the SDK produces, and which span the instrumentor records."""
import json
import sys
from pathlib import Path

import openai

# openai 1.x and 2.x build on `httpx`; newer releases moved to `httpx2`. Use whichever the SDK uses.
_base = [c for c in openai.DefaultHttpxClient.__mro__ if c.__module__.split(".")[0] in ("httpx", "httpx2")][0]
httpx = sys.modules[_base.__module__.split(".")[0]]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from fi_instrumentation import register  # noqa: E402
from fi_instrumentation.fi_types import ProjectType  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from traceai_openai import OpenAIInstrumentor  # noqa: E402

from helicone_tracing import make_client  # noqa: E402

seen = []


def handler(request: httpx.Request) -> httpx.Response:
    seen.append(
        {
            "url": str(request.url),
            "authorization_carries": (
                "helicone-key" if "sk-helicone-fake" in request.headers.get("authorization", "")
                else "openai-key" if "sk-openai-fake" in request.headers.get("authorization", "")
                else "other"
            ),
            "helicone_auth": "present" if request.headers.get("helicone-auth") else "absent",
        }
    )
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        },
    )


exporter = InMemorySpanExporter()
provider = register(
    project_type=ProjectType.OBSERVE,
    project_name="hosted-shape",
    set_global_tracer_provider=False,
    verbose=False,
    span_exporter=exporter,
    batch=False,
)
OpenAIInstrumentor().instrument(tracer_provider=provider)

out = {}
for surface in ("gateway", "proxy"):
    client = make_client(
        surface,
        helicone_key="sk-helicone-fake",
        provider_key="sk-openai-fake",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.chat.completions.create(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
    span = exporter.get_finished_spans()[-1]
    out[surface] = {
        "request": seen[-1],
        "provider_attr": span.attributes.get("gen_ai.provider.name"),
        "model_attr": span.attributes.get("gen_ai.request.model"),
    }
print(json.dumps(out))
