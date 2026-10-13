"""Request a case-level verdict from the draft comparison API.

Exit 0: gate passed; 1: gate failed; 2: request, response or local I/O error.
Requires a JSON request file, BASE_URL and Future AGI API/secret environment vars.
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="Comparison request JSON file")
    parser.add_argument("--output", type=Path, default=Path("release-gate.json"))
    args = parser.parse_args()

    try:
        body = json.loads(args.request.read_text())
        if not isinstance(body, dict) or not isinstance(body.get("release_gate"), dict):
            raise ValueError("Request must contain a release_gate object.")
        for key in ("baseline_run_id", "candidate_run_id", "metric_id"):
            body[key] = str(uuid.UUID(str(body[key])))
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
        result = envelope.get("result") if isinstance(envelope, dict) else None
        gate = result.get("release_gate") if isinstance(result, dict) else None
        if (
            not isinstance(envelope, dict)
            or envelope.get("status") is not True
            or not isinstance(gate, dict)
            or gate.get("verdict") not in ("pass", "fail")
            or any(
                result.get(key) != body.get(key)
                for key in ("baseline_run_id", "candidate_run_id", "metric_id")
            )
        ):
            raise ValueError(
                "Response is missing a valid gate for the requested runs/metric."
            )
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
