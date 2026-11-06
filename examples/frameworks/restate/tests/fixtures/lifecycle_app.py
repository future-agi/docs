"""Synthetic HTTP work around the real Restate ASGI app; never calls a model."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import agent_service
from restate.ext.tracing import _tracing


async def app(scope, receive, send):
    if scope["type"] != "http" or scope["path"] != "/probe":
        # In particular, let Restate handle lifespan and install its real SIGTERM handler.
        return await agent_service.app(scope, receive, send)

    # Stand in for Restate's invocation context, not its signal/lifecycle implementation.
    _tracing.current_context = lambda: SimpleNamespace(
        request=lambda: SimpleNamespace(attempt_headers={
            "traceparent": "00-11111111111111111111111111111111-2222222222222222-01"
        })
    )
    _tracing.get_extension_data = lambda ctx, key: None
    _tracing.set_extension_data = lambda ctx, key, value: None
    Path(os.environ["PROBE_STARTED"]).touch()
    await asyncio.sleep(float(os.environ.get("PROBE_DELAY", "0")))
    await agent_service.get_weather("synthetic", '{"city":"PRIVATE_MARKER"}', False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})
