"""Trace TypeSafe (Jev) System One decisions in Future AGI with traceAI-typesafe.

The block between "recipe start" and "recipe end" is the code the docs page
shows. The rest is a small support-ticket triage app around it, with failure
scenarios, used by run_e2e.sh.

Environment: FI_API_KEY, FI_SECRET_KEY (Future AGI), TYPESAFE_API_KEY
(TypeSafe), optional TYPESAFE_BASE_URL (another System One host) and
FI_BASE_URL (a self-hosted Future AGI collector).

    python app.py --scenario ok          # triage one ticket: sync + async decisions, a session
    python app.py --scenario fail-422    # the API rejects a malformed question (HTTP 422)
    python app.py --scenario fail-auth   # a wrong API key (HTTP 401)
    python app.py --scenario fail-asset  # an image file that does not exist (client-side error)

RUN_MARKER (optional) is added to the ticket text (also as an email address) and the
question wording, so a privacy check can search the stored traces for it.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
import uuid
from pathlib import Path

from fi_instrumentation import FITracer, using_session
from fi_instrumentation.fi_types import FiSpanKindValues
from opentelemetry.trace import Status, StatusCode

# --- recipe start ---
import os

from fi_instrumentation import register
from fi_instrumentation.fi_types import ProjectType
from traceai_typesafe import TypeSafeInstrumentor
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score, TypeSafeClient

trace_provider = register(
    project_type=ProjectType.OBSERVE,
    project_name=os.environ.get("FI_PROJECT_NAME", "support-triage"),
)
TypeSafeInstrumentor().instrument(tracer_provider=trace_provider)
# --- recipe end ---

MARKER = os.environ.get("RUN_MARKER", "")
TICKET = (
    "Order 1042: I was charged twice for the same order and nobody answers my emails. "
    "Please refund the duplicate today. {0}".format(MARKER)
).strip()
if MARKER:  # privacy check: an email address in the content too
    TICKET += " Reply to {0}@example.com.".format(MARKER)

# --- questions start ---
QUESTIONS = {
    "billing": Noul(instructions="Is this message about billing? {0}".format(MARKER).strip()),
    "tone": Choice(
        instructions="What is the tone of this message?",
        criteria={"calm": None, "angry": "Upset or hostile {0}".format(MARKER).strip(), "excited": None},
    ),
    "urgency": Score(
        instructions="How urgent is this message?",
        criteria=["Can wait", "Needs attention this week", "Needs attention today"],
    ),
}
# --- questions end ---

tracer = FITracer(trace_provider.get_tracer("support-triage"))


def triage_sync() -> None:
    # --- sync call start ---
    with TypeSafeClient() as client:
        result = client.system_one(state=TICKET, questions=QUESTIONS)
    print("billing", result.nouls["billing"].noul)
    print("tone", result.choices["tone"].choice, result.choices["tone"].confidence)
    print("urgency", result.scores["urgency"].score, result.scores["urgency"].confidence)
    # --- sync call end ---
    print("RESULT model", result.model, "tokens", result.usage.input_tokens, result.usage.output_tokens)
    with TypeSafeClient() as client:
        models = client.models.list()  # GET /v1/models: not a decision, no span
    print("RESULT models", [model.name for model in models.models])


async def triage_async() -> None:
    # --- async call start ---
    async with AsyncTypeSafeClient() as client:
        result = await client.system_one(
            state={"ticket": TICKET, "customer_tier": "gold"},
            questions={"escalate": Noul(instructions="Should a human agent take this ticket now?")},
        )
    print("escalate", result.nouls["escalate"].noul)
    # --- async call end ---


def fail_422() -> None:
    with TypeSafeClient() as client:
        # A choice question needs a mapping of criteria; a list passes the SDK's
        # own check and is rejected by the API.
        client.system_one(
            state=TICKET,
            questions={"tone": {"type": "choice", "instructions": "Tone?", "criteria": ["calm", "angry"]}},
        )


def fail_auth() -> None:
    with TypeSafeClient(api_key="ts-invalid-e2e-key") as client:
        client.system_one(state=TICKET, questions={"billing": QUESTIONS["billing"]})


def fail_asset() -> None:
    from typesafe_sdk import Image

    missing = Path(tempfile.gettempdir()) / "typesafe-e2e-{0}".format(MARKER or "x") / "photo.png"
    photo = Image(missing)
    with TypeSafeClient() as client:
        client.system_one(
            state="Product photo: {0}".format(photo),
            questions={"damaged": Noul(instructions="Is the product damaged?")},
            assets={"photo": photo},
        )


SCENARIOS = {
    "ok": lambda: (triage_sync(), asyncio.run(triage_async())),
    "fail-422": fail_422,
    "fail-auth": fail_auth,
    "fail-asset": fail_asset,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="ok")
    args = parser.parse_args()
    session_id = "triage-" + uuid.uuid4().hex[:12]
    outcome = "ok"
    with using_session(session_id):
        # The app's own parent span. It records no exception text of its own.
        with tracer.start_as_current_span(
            "triage_ticket",
            fi_span_kind=FiSpanKindValues.CHAIN,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            span.set_input(TICKET)
            trace_id = "{0:032x}".format(span.get_span_context().trace_id)
            try:
                SCENARIOS[args.scenario]()
                span.set_output("triaged")
                span.set_status(Status(StatusCode.OK))
            except Exception as error:  # the failure scenarios end here
                outcome = type(error).__name__
                span.set_status(Status(StatusCode.ERROR, outcome))
    trace_provider.force_flush()
    print("RESULT scenario={0} outcome={1} trace_id={2} session_id={3}".format(args.scenario, outcome, trace_id, session_id))
    trace_provider.shutdown()
    return 0 if (outcome == "ok") == (args.scenario == "ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
