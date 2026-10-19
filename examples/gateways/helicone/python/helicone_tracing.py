"""Trace OpenAI-client calls that go through Helicone, with Future AGI (the code the docs page shows).

Two Helicone surfaces, two different auths. Keep them apart:

  AI Gateway     base URL  https://ai-gateway.helicone.ai
                 api_key   = your Helicone key              (no Helicone-Auth header)
  classic proxy  base URL  https://oai.helicone.ai/v1
                 api_key   = your OpenAI key
                 header    Helicone-Auth: Bearer <your Helicone key>

Future AGI credentials (FI_API_KEY / FI_SECRET_KEY) are read by `register()` from the
environment and go to the Future AGI collector only. Helicone keys go to Helicone only.
"""
from __future__ import annotations

import os
from typing import Optional

from fi_instrumentation import register
from fi_instrumentation.fi_types import ProjectType
from openai import OpenAI
from traceai_openai import OpenAIInstrumentor

GATEWAY = "gateway"
PROXY = "proxy"

# Base URLs from Helicone's own docs, read 2026-10-15. See the docs page for the sources.
DEFAULT_BASE_URL = {
    GATEWAY: "https://ai-gateway.helicone.ai",
    PROXY: "https://oai.helicone.ai/v1",
}


def setup_tracing(project_name: str, *, scrub_error_details: bool = False):
    """register() the Future AGI project and instrument the OpenAI client.

    scrub_error_details=True wraps the exporter so exception messages, stack traces and
    the status message are dropped before export (see redact_errors.py). The hide
    settings (FI_HIDE_INPUTS / FI_HIDE_OUTPUTS) do not cover those.
    """
    kwargs = {}
    if scrub_error_details:
        from fi_instrumentation import HTTPSpanExporter
        from redact_errors import RedactErrorDetailsExporter

        kwargs["span_exporter"] = RedactErrorDetailsExporter(HTTPSpanExporter())
    provider = register(
        project_type=ProjectType.OBSERVE,
        project_name=project_name,
        set_global_tracer_provider=False,
        verbose=False,
        **kwargs,
    )
    OpenAIInstrumentor().instrument(tracer_provider=provider)
    return provider


def make_client(
    surface: str,
    *,
    helicone_key: str,
    provider_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **client_kwargs,
) -> OpenAI:
    """Build the OpenAI client for one Helicone surface.

    Create the client after instrument(); the instrumentor patches the SDK, so any
    client created from it is traced.
    """
    base_url = base_url or DEFAULT_BASE_URL[surface]
    if surface == GATEWAY:
        # The Helicone key is the OpenAI api_key. No Helicone-Auth header here.
        return OpenAI(base_url=base_url, api_key=helicone_key, **client_kwargs)
    if surface == PROXY:
        if not provider_key:
            raise ValueError("the classic proxy needs your OpenAI key as api_key")
        return OpenAI(
            base_url=base_url,
            api_key=provider_key,
            default_headers={"Helicone-Auth": f"Bearer {helicone_key}"},
            **client_kwargs,
        )
    raise ValueError(f"unknown surface {surface!r}; use 'gateway' or 'proxy'")


def env_client(surface: Optional[str] = None, **client_kwargs) -> OpenAI:
    """make_client() from HELICONE_* environment variables (what run_demo.py uses)."""
    surface = surface or os.environ.get("HELICONE_SURFACE", GATEWAY)
    return make_client(
        surface,
        helicone_key=os.environ["HELICONE_API_KEY"],
        provider_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("HELICONE_BASE_URL"),
        **client_kwargs,
    )
