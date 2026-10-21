"""The stand-in speaks the published System One contract to the real typesafe-sdk client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

typesafe_sdk = pytest.importorskip("typesafe_sdk")
from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeClient  # noqa: E402


def _client(stub, **kwargs):
    kwargs.setdefault("api_key", "standin-key")
    return TypeSafeClient(base_url=stub, retry=RetryPolicy(max_retries=0), **kwargs)


def test_answers_parse_into_the_sdk_types(stub):
    with _client(stub) as client:
        result = client.system_one(
            state="I was charged twice.",
            questions={
                "billing": Noul(instructions="Billing?"),
                "tone": Choice(instructions="Tone?", criteria={"calm": None, "angry": None}),
                "urgency": Score(instructions="Urgent?", criteria=["low", "high"]),
            },
        )
    assert result.model == "jev-1.13.0"  # jev-latest resolved, as documented for aliases
    assert 0 < result.nouls["billing"].noul < 1
    assert result.choices["tone"].choice in {"calm", "angry"}
    assert set(result.choices["tone"].probabilities) == {"calm", "angry"}
    assert 0 <= result.scores["urgency"].score <= 1
    assert result.scores["urgency"].legend == {0: "low", 1: "high"}
    assert result.usage.input_tokens > 0 and result.usage.output_tokens == 6
    assert result.request_id.startswith("req_standin_")


def test_noul_has_no_confidence_on_the_wire(stub):
    with _client(stub) as client:
        result = client.system_one(state="x", questions={"q": Noul(instructions="ok?")})
    raw = json.loads(result.raw_http_response.content)
    assert raw["answers"]["q"] == {"type": "noul", "noul": result.nouls["q"].noul}


def test_errors_use_the_documented_bodies(stub):
    from typesafe_sdk import TypeSafeAuthenticationError, TypeSafeUnprocessableEntityError

    with _client(stub, api_key="ts-invalid-x") as client:
        with pytest.raises(TypeSafeAuthenticationError) as raised:
            client.system_one(state="x", questions={"q": Noul(instructions="ok?")})
    assert raised.value.body["detail"]["error_type"] == "authentication_error"
    with _client(stub) as client:
        with pytest.raises(TypeSafeUnprocessableEntityError) as raised:
            client.system_one(state="x", questions={"t": {"type": "choice", "criteria": ["a", "b"]}})
    assert raised.value.body["detail"][0]["loc"] == ["body", "questions", "t", "choice", "criteria"]
    request = urllib.request.Request(stub + "/v1/systemone", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as no_key:
        urllib.request.urlopen(request)
    assert no_key.value.code == 403


def test_models_list(stub):
    with _client(stub) as client:
        names = [model.name for model in client.models.list().models]
    assert names == ["jev-latest", "jev-1.13.0"]


def test_binds_loopback_only(stub):
    assert stub.startswith("http://127.0.0.1:")
