"""Request a case-level verdict from the draft comparison API.

Exit 0: gate passed; 1: gate failed; 2: request, response or local I/O error.
Requires a JSON request file, BASE_URL and Future AGI API/secret environment vars.
"""

import argparse
import json
import os
import sys
import uuid
from math import isfinite
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _normalise_request(body):
    """Apply the server's small gate defaults before sending and validating."""
    if not isinstance(body, dict) or not isinstance(body.get("release_gate"), dict):
        raise ValueError("Request must contain a release_gate object.")
    body = dict(body)
    for key in ("baseline_run_id", "candidate_run_id", "metric_id"):
        body[key] = str(uuid.UUID(str(body[key])))
    gate = body["release_gate"]
    if set(gate) - {"max_regressions", "critical_cases"}:
        raise ValueError("release_gate contains an unknown field.")
    max_regressions = gate.get("max_regressions", 0)
    if type(max_regressions) is not int or max_regressions < 0:
        raise ValueError("max_regressions must be a nonnegative integer.")
    critical_cases = gate.get("critical_cases", [])
    if not isinstance(critical_cases, list):
        raise ValueError("critical_cases must be an array.")
    normalised_critical = []
    seen = set()
    for case in critical_cases:
        if not isinstance(case, dict) or set(case) != {"example_id", "trial_number"}:
            raise ValueError(
                "critical_cases must contain only example_id and trial_number."
            )
        identity = (str(uuid.UUID(str(case["example_id"]))), case["trial_number"])
        if type(identity[1]) is not int or identity[1] < 1 or identity in seen:
            raise ValueError("critical case identities must be unique positive trials.")
        seen.add(identity)
        normalised_critical.append(
            {"example_id": identity[0], "trial_number": identity[1]}
        )
    body["release_gate"] = {
        "max_regressions": max_regressions,
        "critical_cases": sorted(
            normalised_critical,
            key=lambda item: (item["example_id"], item["trial_number"]),
        ),
    }
    if "higher_is_better" not in body:
        body["higher_is_better"] = True
    if type(body["higher_is_better"]) is not bool:
        raise ValueError("higher_is_better must be a boolean.")
    if "passing_score" in body and body["passing_score"] is not None:
        if isinstance(body["passing_score"], bool) or not isinstance(
            body["passing_score"], (int, float)
        ):
            raise ValueError("passing_score must be finite or null.")
        try:
            finite = isfinite(float(body["passing_score"]))
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            raise ValueError("passing_score must be finite or null.")
    else:
        body["passing_score"] = None
    return body


def _validate_response(envelope, body):
    if not isinstance(envelope, dict) or envelope.get("status") is not True:
        raise ValueError("Response did not contain a successful envelope.")
    result = envelope.get("result")
    gate = result.get("release_gate") if isinstance(result, dict) else None
    required = {
        "verdict",
        "expected_count",
        "comparable_count",
        "regression_count",
        "policy",
        "passing_score",
        "higher_is_better",
        "blockers",
    }
    if (
        not isinstance(result, dict)
        or not isinstance(gate, dict)
        or not required <= set(gate)
    ):
        raise ValueError("Response is missing a complete release-gate report.")
    for key in ("baseline_run_id", "candidate_run_id", "metric_id"):
        if result.get(key) != body[key]:
            raise ValueError("Response does not match the requested runs or metric.")
    echoed = dict(body)
    echoed["release_gate"] = gate["policy"]
    echoed["passing_score"] = gate["passing_score"]
    echoed["higher_is_better"] = gate["higher_is_better"]
    normalised_echo = _normalise_request(echoed)
    if gate["policy"] != normalised_echo["release_gate"] or any(
        normalised_echo[key] != body[key]
        for key in ("release_gate", "passing_score", "higher_is_better")
    ):
        raise ValueError("Response gate settings do not match the request.")
    if gate["verdict"] not in ("pass", "fail") or not all(
        type(gate[key]) is int and gate[key] >= 0
        for key in ("expected_count", "comparable_count", "regression_count")
    ):
        raise ValueError("Response contains invalid gate counts or verdict.")
    if (
        gate["comparable_count"] > gate["expected_count"]
        or gate["regression_count"] > gate["comparable_count"]
    ):
        raise ValueError("Response gate counts are inconsistent.")
    if not isinstance(gate["blockers"], list) or any(
        not isinstance(item, dict) for item in gate["blockers"]
    ):
        raise ValueError("Response blockers are invalid.")
    if gate["verdict"] == "pass" and (
        gate["expected_count"] == 0
        or gate["comparable_count"] != gate["expected_count"]
        or gate["blockers"]
        or gate["regression_count"] > body["release_gate"]["max_regressions"]
    ):
        raise ValueError("Response claims pass despite failed gate conditions.")
    if gate["verdict"] == "fail" and not gate["blockers"]:
        raise ValueError("Response claims fail without a blocker.")
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="Comparison request JSON file")
    parser.add_argument("--output", type=Path, default=Path("release-gate.json"))
    args = parser.parse_args()

    try:
        body = _normalise_request(json.loads(args.request.read_text()))
        request = Request(
            os.environ["BASE_URL"].rstrip("/") + "/model-hub/experiment-runs/compare/",
            data=json.dumps(body, allow_nan=False).encode(),
            method="POST",
            headers={
                "X-Api-Key": os.environ["FUTURE_AGI_API_KEY"],
                "X-Secret-Key": os.environ["FUTURE_AGI_SECRET_KEY"],
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=30) as response:
            envelope = json.load(response)
        gate = _validate_response(envelope, body)
        args.output.write_text(json.dumps(envelope, indent=2, allow_nan=False) + "\n")
        print(f"Gate {gate['verdict']}; report saved to {args.output}")
        return 0 if gate["verdict"] == "pass" else 1
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as error:
        # Replace any stale success artifact when the request cannot be evaluated.
        failure = {"status": False, "error": str(error)}
        try:
            args.output.write_text(json.dumps(failure, indent=2) + "\n")
        except OSError:
            pass
        print(f"Gate request failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
