import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M81TestProfileTests(unittest.TestCase):
    def _run_profile_dry_run(self, profile, *extra_args, check=True):
        environment = os.environ.copy()
        # The contract tests exercise explicit CLI configuration.  Production
        # Docker images intentionally provide a default env value, so do not
        # let that deployment setting change the dry-run branch under test.
        environment.pop("SPATIAL_AGENT_DATASET_CONFIG", None)
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                profile,
                *extra_args,
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=check,
            capture_output=True,
            text=True,
            env=environment,
        )

    def _profile_payload(self, profile, *extra_args):
        completed = self._run_profile_dry_run(profile, *extra_args)
        return json.loads(completed.stdout)

    def test_profile_runner_handles_utf8_child_output(self):
        from scripts.test_profile import ProfileCommand, _run_command

        result = _run_command(
            ProfileCommand(
                "utf8_output",
                [sys.executable, "-c", "print('中文阶段输出')"],
            )
        )

        self.assertTrue(result["ok"])
        self.assertIn("中文阶段输出", result["stdout_tail"])

    def test_quick_profile_is_bounded_to_compact_gate(self):
        payload = self._profile_payload("quick")
        names = [item["name"] for item in payload["commands"]]

        self.assertEqual(names, ["core_contract_tripwires"])
        core_args = payload["commands"][0]["command"]
        selected_tests = [item for item in core_args if item.startswith("tests.")]
        self.assertEqual(len(selected_tests), 2)
        self.assertEqual(
            selected_tests,
            [
                "tests.test_dev_gate.DevGateTests.test_runtime_result_and_artifact_share_contract",
                "tests.test_dev_gate.DevGateTests.test_clarification_follow_up_is_session_scoped",
            ],
        )

    def test_smoke_profile_does_not_request_nested_full_suite(self):
        payload = self._profile_payload("smoke")

        self.assertEqual([item["name"] for item in payload["commands"]], ["service_smoke"])
        self.assertEqual(payload["commands"][0]["env"], {})

    def test_ci_profile_has_no_nested_stage_suite(self):
        payload = self._profile_payload("ci")

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["core_contract_tripwires", "service_smoke"],
        )

    def test_stage_profile_uses_small_acceptance_examples(self):
        payload = self._profile_payload("stage")

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["stage_acceptance_examples"],
        )
        stage_args = payload["commands"][0]["command"]
        self.assertIn("--cases", stage_args)
        self.assertTrue(stage_args[stage_args.index("--cases") + 1].endswith("stage-acceptance.json"))
        self.assertIn("--no-model-evaluation", stage_args)
        self.assertIn("--no-model-replay", stage_args)

    def test_full_stage_profile_keeps_the_heavy_gate_explicit(self):
        payload = self._profile_payload("full-stage")

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["strict_global_offline_evaluation"],
        )
        global_args = payload["commands"][0]["command"]
        self.assertNotIn("--no-model-evaluation", global_args)
        self.assertNotIn("--no-model-replay", global_args)

    def test_full_regression_profile_opt_in_bypasses_compact_hook(self):
        payload = self._profile_payload("full-regression")

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["historical_unittest_discovery"],
        )
        command = payload["commands"][0]
        self.assertEqual(command["env"], {})
        self.assertEqual(
            command["command"][-4:],
            ["discover", "-s", "tests", "-v"],
        )

    def test_full_regression_report_is_bounded_and_classified(self):
        from scripts.test_profile import _parse_unittest_report

        report = _parse_unittest_report(
            """test_ok (tests.test_sample.SampleTests.test_ok) ... ok

======================================================================
FAIL: test_bad (tests.test_sample.SampleTests.test_bad)
----------------------------------------------------------------------
AssertionError: expected value

======================================================================
ERROR: test_import (tests.test_other.OtherTests.test_import)
----------------------------------------------------------------------
ImportError: No module named optional_package

----------------------------------------------------------------------
Ran 3 tests in 0.01s

FAILED (failures=1, errors=1, skipped=0)
"""
        )

        self.assertEqual(report["counts"], {
            "failures": 1,
            "errors": 1,
            "skipped": 0,
            "total": 3,
            "passed": 1,
        })
        self.assertEqual(report["by_category"]["assertion_contract"], 1)
        self.assertEqual(report["by_category"]["environment_or_dependency"], 1)
        self.assertTrue(all("AssertionError" not in item for item in report["failures"]))

        payload = self._profile_payload("gis-core")
        command = payload["commands"][0]
        selected_tests = [item for item in command["command"] if item.startswith("tests.")]

        self.assertEqual(command["name"], "gis_core_examples")
        self.assertEqual(len(selected_tests), 3)
        self.assertNotIn("tests.test_m15_raster_metadata", command["command"])

    def test_live_short_profile_uses_only_representative_cases(self):
        payload = self._profile_payload(
            "live-short",
            "--dataset-config",
            "D:/tmp/wuhan-gis/datasets.wuhan.analysis-ready.bound.json",
            "--live-output",
            "D:/tmp/wuhan-gis/test-live-short.json",
        )
        command = payload["commands"][0]
        args = command["command"]
        case_ids = args[args.index("--case-ids") + 1]

        self.assertEqual(
            case_ids,
            "live-gis-spatial-overview,live-gis-constrained-buildability",
        )
        self.assertEqual(command["env"]["SPATIAL_AGENT_LIVE_OPENAI"], "1")
        self.assertEqual(command["env"]["SPATIAL_AGENT_LIVE_GIS"], "1")
        self.assertEqual(
            command["env"]["SPATIAL_AGENT_DATASET_CONFIG"],
            "D:/tmp/wuhan-gis/datasets.wuhan.analysis-ready.bound.json",
        )

    def test_live_short_local_requires_explicit_dataset_config(self):
        completed = self._run_profile_dry_run("live-short", check=False)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("requires --dataset-config", completed.stderr)


if __name__ == "__main__":
    unittest.main()
