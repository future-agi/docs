#!/usr/bin/env python3
"""Run the example handler in-process, the way the Lambda runtime does: one import (cold start),
then several invocations (warm). Pointed at a real Future AGI through the FI_* environment.

    local_runner.py happy|failure|privacy|nokeys [--marker TEXT]

The context is a stand-in for the Lambda context (request id and remaining time). Nothing here
calls AWS.
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
FIX = HERE / "tests" / "fixtures"


class Ctx:
    def __init__(self, n):
        self.aws_request_id = f"local-req-{n:04d}"

    def get_remaining_time_in_millis(self):
        return 30_000


def events(marker):
    note = marker or "demo"
    apigw = json.loads((FIX / "apigw_v2.json").read_text())
    apigw["body"] = json.dumps({"order_id": "A-100", "note": note})
    apigw["headers"]["x-demo-header"] = note  # headers are never exported
    sqs = json.loads((FIX / "sqs.json").read_text())
    sqs["Records"][0]["body"] = json.dumps({"order_id": "A-200", "note": note})
    return apigw, {"order_id": "A-300", "note": note}, sqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["happy", "failure", "privacy", "nokeys"])
    ap.add_argument("--marker", default="")
    a = ap.parse_args()
    import handler  # import = cold start: the provider is built here, once

    apigw, direct, sqs = events(a.marker)
    if a.scenario in ("happy", "privacy", "nokeys"):
        for n, ev in enumerate([apigw, direct, sqs], 1):
            print("returned", handler.lambda_handler(ev, Ctx(n))["status"])
    if a.scenario in ("failure", "privacy"):
        try:
            handler.lambda_handler({"order_id": "boom", "note": a.marker or "demo"}, Ctx(9))
        except ValueError as exc:
            print("raised", type(exc).__name__)
        print("returned", handler.lambda_handler(direct, Ctx(10))["status"])
    print("providers_built", handler.tracing.providers_built)
    return 0


if __name__ == "__main__":
    sys.exit(main())
