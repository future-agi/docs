"""Compare a caller-owned workflow through the draft Future AGI run APIs.

Requires Python 3.10+, a compatible test deployment, an existing dataset and
an evaluator binding for the exact-match rule used below. No model is called.
"""

import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    base_url = os.environ["BASE_URL"].rstrip("/")
    dataset_id = os.environ["DATASET_ID"]
    metric_id = str(uuid.UUID(os.environ["METRIC_ID"]))
    headers = {
        "X-Api-Key": os.environ["FUTURE_AGI_API_KEY"],
        "X-Secret-Key": os.environ["FUTURE_AGI_SECRET_KEY"],
        "Content-Type": "application/json",
    }

    def api(method, path, body=None):
        data = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = Request(base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                envelope = json.load(response)
        except HTTPError as error:
            detail = error.read(4096).decode(errors="replace")
            raise RuntimeError(
                f"{method} {path}: HTTP {error.code}: {detail}"
            ) from error
        if envelope.get("status") is not True:
            raise RuntimeError(f"Request did not succeed: {envelope}")
        return envelope["result"]

    cases = [
        {"external_id": "shipping", "input": {"topic": "shipping"}, "expected": 5},
        {"external_id": "returns", "input": {"topic": "returns"}, "expected": 30},
    ]
    version = api(
        "POST",
        f"/model-hub/datasets/{dataset_id}/versions/",
        {
            "description": "External workflow comparison tutorial",
            "source_revision": "external-run-comparison-v1",
            "items": cases,
        },
    )
    snapshot = api("GET", f"/model-hub/datasets/{dataset_id}/versions/{version['id']}/")
    items = snapshot["items"]
    assert len(items) == 2 and snapshot["has_more"] is False

    def retrieve_policy(topic, config):
        return {"days": config[topic], "unit": "days"}

    def apply_policy(document):
        return int(document["days"])

    def task(case_input, config):
        # Replace this function with your agent, tool loop, or remote task call.
        document = retrieve_policy(case_input["topic"], config)
        return apply_policy(document)

    runs = {}
    payloads = {}
    for label, config in (
        ("baseline", {"shipping": 5, "returns": 14}),
        ("candidate", {"shipping": 3, "returns": 30}),
    ):
        create_body = {
            "run_id": str(uuid.uuid4()),
            "dataset_version_id": version["id"],
            "expected_items": [
                {"example_id": item["example_id"], "trial_number": 1} for item in items
            ],
            "evaluator_metric_ids": [metric_id],
            "model_config": config,
            "metadata": {"name": label, "task_revision": "external-workflow-v1"},
        }
        run = api("POST", "/model-hub/experiment-runs/", create_body)
        replay = api("POST", "/model-hub/experiment-runs/", create_body)
        assert replay == run
        binding = next(
            b for b in run["evaluator_bindings"] if b["metric_id"] == metric_id
        )
        results = []
        for item in items:
            output = task(item["input"], config)
            results.append(
                {
                    "example_id": item["example_id"],
                    "trial_number": 1,
                    "receipt_key": str(uuid.uuid4()),
                    "status": "completed",
                    "output": output,
                    "score_refs": [
                        {
                            "metric_id": metric_id,
                            "evaluator_version_id": binding["evaluator_version_id"],
                            "status": "assessed",
                            "value": int(output == item["expected"]),
                            "explanation": "Exact match between output and expected days.",
                        }
                    ],
                }
            )
        runs[label] = run
        payloads[label] = results

    compare_body = {
        "baseline_run_id": runs["baseline"]["id"],
        "candidate_run_id": runs["candidate"]["id"],
        "metric_id": metric_id,
        "passing_score": 1,
        "higher_is_better": True,
    }
    for label in ("baseline", "candidate"):
        path = f"/model-hub/experiment-runs/{runs[label]['id']}/results/"
        results = payloads[label]
        api("POST", path, {"items": results[:1]})
        if label == "candidate":
            incomplete = api(
                "POST", "/model-hub/experiment-runs/compare/", compare_body
            )
            assert incomplete["candidate_counts"]["missing"] == 1
            print("Before the last result: candidate missing=1")
        complete = api("POST", path, {"items": results[1:]})
        replay = api("POST", path, {"items": results[1:]})
        assert complete == replay
        assert complete["run"]["status"] == "completed"

    comparison = api("POST", "/model-hub/experiment-runs/compare/", compare_body)
    summary = comparison["comparison"]
    assert summary["baseline"]["score_average"] == 0.5
    assert summary["candidate"]["score_average"] == 0.5
    assert summary["status_counts"]["regressed"] == 1
    assert summary["status_counts"]["improved"] == 1
    assert comparison["candidate_counts"]["missing"] == 0
    Path("comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    print("Baseline mean=0.5; candidate mean=0.5")
    print("Case outcomes: improved=1, regressed=1, missing=0")
    print("Create replay and terminal result replay preserved the original records.")
    print("Saved full evidence to comparison.json")


if __name__ == "__main__":
    main()
