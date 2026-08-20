import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M81TestProfileTests(unittest.TestCase):
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

    def test_quick_profile_is_bounded_to_core_tripwires(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "quick",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        names = [item["name"] for item in payload["commands"]]

        self.assertEqual(names, ["core_contract_tripwires"])
        core_args = payload["commands"][0]["command"]
        selected_tests = [item for item in core_args if item.startswith("tests.")]
        self.assertEqual(len(selected_tests), 3)
        self.assertNotIn("tests.test_m68_workflow_templates", core_args)
        self.assertNotIn("tests.test_m69_workflow_runtime", core_args)
        self.assertNotIn("tests.test_m77_request_model", core_args)

    def test_smoke_profile_does_not_request_nested_full_suite(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "smoke",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual([item["name"] for item in payload["commands"]], ["service_smoke"])
        self.assertEqual(payload["commands"][0]["env"], {})

    def test_ci_profile_keeps_only_one_stage_representative(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "ci",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["core_contract_tripwires", "service_smoke", "ci_stage_representative"],
        )
        ci_args = payload["commands"][2]["command"]
        self.assertEqual(ci_args[ci_args.index("--case-ids") + 1], "stage-spatial-analysis")
        self.assertIn("--no-model-evaluation", ci_args)
        self.assertIn("--no-model-replay", ci_args)

    def test_stage_profile_uses_small_acceptance_examples(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "stage",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["core_contract_tripwires", "stage_acceptance_examples"],
        )
        stage_args = payload["commands"][1]["command"]
        self.assertIn("--cases", stage_args)
        self.assertTrue(stage_args[stage_args.index("--cases") + 1].endswith("stage-acceptance.json"))
        self.assertIn("--no-model-evaluation", stage_args)
        self.assertIn("--no-model-replay", stage_args)

    def test_full_stage_profile_keeps_the_heavy_gate_explicit(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "full-stage",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(
            [item["name"] for item in payload["commands"]],
            ["core_contract_tripwires", "service_smoke", "strict_global_offline_evaluation"],
        )
        global_args = payload["commands"][2]["command"]
        self.assertNotIn("--no-model-evaluation", global_args)
        self.assertNotIn("--no-model-replay", global_args)

    def test_gis_core_profile_is_sampled_not_full_modules(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "gis-core",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        command = payload["commands"][0]
        selected_tests = [item for item in command["command"] if item.startswith("tests.")]

        self.assertEqual(command["name"], "gis_core_examples")
        self.assertEqual(len(selected_tests), 3)
        self.assertNotIn("tests.test_m15_raster_metadata", command["command"])

    def test_live_short_profile_uses_only_representative_cases(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "live-short",
                "--dataset-config",
                "D:/tmp/wuhan-gis/datasets.wuhan.analysis-ready.bound.json",
                "--live-output",
                "D:/tmp/wuhan-gis/test-live-short.json",
                "--dry-run",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
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
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "test_profile.py"),
                "--profile",
                "live-short",
                "--dry-run",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("requires --dataset-config", completed.stderr)


if __name__ == "__main__":
    unittest.main()
