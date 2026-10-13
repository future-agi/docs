import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

SCRIPT = Path(__file__).parents[2] / "public" / "cookbook" / "check-experiment-run.py"
spec = importlib.util.spec_from_file_location("check_experiment_run", SCRIPT)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
IDS = {
    name: f"00000000-0000-4000-8000-{number:012}"
    for number, name in enumerate(
        ("baseline_run_id", "candidate_run_id", "metric_id"), 1
    )
}


def request():
    return {**IDS, "release_gate": {}}


def response(body=None):
    body = cli._normalise_request(body or request())
    return {
        "status": True,
        "result": {
            **IDS,
            "release_gate": {
                "verdict": "pass",
                "expected_count": 2,
                "comparable_count": 2,
                "regression_count": 0,
                "policy": body["release_gate"],
                "passing_score": body["passing_score"],
                "higher_is_better": body["higher_is_better"],
                "blockers": [],
            },
        },
    }


class ReleaseGateCLITest(unittest.TestCase):
    def run_cli(self, result, body=None, error=None):
        with tempfile.TemporaryDirectory() as directory:
            request_file, output_file = (
                Path(directory) / "request.json",
                Path(directory) / "report.json",
            )
            request_file.write_text(json.dumps(request() if body is None else body))
            output_file.write_text(json.dumps({"status": True, "old": "success"}))
            with (
                patch.object(
                    sys,
                    "argv",
                    [str(SCRIPT), str(request_file), "--output", str(output_file)],
                ),
                patch.dict(
                    os.environ,
                    {
                        "BASE_URL": "http://example.invalid",
                        "FUTURE_AGI_API_KEY": "key",
                        "FUTURE_AGI_SECRET_KEY": "secret",
                    },
                ),
                patch.object(
                    cli,
                    "urlopen",
                    return_value=io.StringIO(json.dumps(result)),
                    side_effect=error,
                ) as opened,
                patch("sys.stdout", new_callable=io.StringIO),
                patch("sys.stderr", new_callable=io.StringIO),
            ):
                code = cli.main()
            saved = json.loads(output_file.read_text())
            sent = json.loads(opened.call_args.args[0].data) if opened.called else None
            self.assertNotIn("old", saved)
            return code, saved, sent

    def test_three_forged_pass_reports_fail_closed(self):
        incomplete = response()
        incomplete["result"]["release_gate"] = {"verdict": "pass"}
        wrong_policy = response()
        wrong_policy["result"]["release_gate"]["policy"]["max_regressions"] = 100
        contradictory = response()
        contradictory["result"]["release_gate"].update(
            comparable_count=0, blockers=[{"reason": "missing"}]
        )
        for payload in (incomplete, wrong_policy, contradictory):
            with self.subTest(payload=payload):
                code, saved, _ = self.run_cli(payload)
                self.assertEqual(code, 2)
                self.assertFalse(saved["status"])

    def test_valid_pass_defaults_and_additive_response_fields(self):
        payload = response()
        payload["result"]["release_gate"]["future_field"] = "accepted"
        code, saved, sent = self.run_cli(payload)
        self.assertEqual(code, 0)
        self.assertEqual(saved, payload)
        self.assertEqual(
            sent["release_gate"], {"max_regressions": 0, "critical_cases": []}
        )
        self.assertIsNone(sent["passing_score"])
        self.assertTrue(sent["higher_is_better"])

    def test_valid_failed_gate_is_saved_and_exits_one(self):
        payload = response()
        payload["result"]["release_gate"].update(
            verdict="fail",
            regression_count=1,
            blockers=[
                {
                    "example_id": IDS["baseline_run_id"],
                    "trial_number": 1,
                    "reason": "regression_limit_exceeded",
                }
            ],
        )
        code, saved, _ = self.run_cli(payload)
        self.assertEqual(code, 1)
        self.assertEqual(saved, payload)

    def test_response_settings_and_count_types_are_checked(self):
        for field, value in (
            ("higher_is_better", False),
            ("higher_is_better", 1),
            ("passing_score", 1),
            ("passing_score", True),
            ("expected_count", True),
            ("regression_count", -1),
            ("regression_count", 3),
            ("verdict", "unknown"),
        ):
            with self.subTest(field=field, value=value):
                payload = response()
                payload["result"]["release_gate"][field] = value
                code, saved, _ = self.run_cli(payload)
                self.assertEqual(code, 2)
                self.assertFalse(saved["status"])
        body = {**request(), "release_gate": {"max_regressions": 1}}
        payload = response(body)
        payload["result"]["release_gate"]["policy"]["max_regressions"] = True
        self.assertEqual(self.run_cli(payload, body=body)[0], 2)

    def test_incomplete_empty_and_over_budget_passes_are_rejected(self):
        for changes in (
            {"expected_count": 0, "comparable_count": 0},
            {"comparable_count": 1},
            {"regression_count": 1},
            {"blockers": [{}]},
            {"verdict": "fail"},
        ):
            payload = response()
            payload["result"]["release_gate"].update(changes)
            self.assertEqual(self.run_cli(payload)[0], 2)

    def test_identity_mismatch_and_transport_error_replace_stale_success(self):
        payload = response()
        payload["result"]["candidate_run_id"] = IDS["baseline_run_id"]
        self.assertEqual(self.run_cli(payload)[0], 2)
        code, saved, _ = self.run_cli({}, error=URLError("unavailable"))
        self.assertEqual(code, 2)
        self.assertFalse(saved["status"])

    def test_critical_case_normalization_preserves_trials_and_policy(self):
        critical = [
            {"example_id": IDS["candidate_run_id"].upper(), "trial_number": 2},
            {"example_id": IDS["baseline_run_id"], "trial_number": 1},
        ]
        body = {
            **request(),
            "release_gate": {"critical_cases": critical},
            "passing_score": 0.5,
            "higher_is_better": False,
        }
        code, _, sent = self.run_cli(response(body), body=body)
        self.assertEqual(code, 0)
        self.assertEqual(sent["release_gate"]["critical_cases"][0]["trial_number"], 1)
        self.assertEqual(sent["release_gate"]["critical_cases"][1]["trial_number"], 2)

    def test_invalid_request_and_huge_threshold_fail_with_error_artifact(self):
        for body in (
            [],
            {},
            {**request(), "passing_score": 10**1000},
            {**request(), "release_gate": {"unexpected": True}},
        ):
            code, saved, sent = self.run_cli({}, body=body)
            self.assertEqual(code, 2)
            self.assertFalse(saved["status"])
            self.assertIsNone(sent)


if __name__ == "__main__":
    unittest.main()
