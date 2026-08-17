import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class M81TestProfileTests(unittest.TestCase):
    def test_quick_profile_is_bounded_and_skips_nested_full_suite(self):
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

        self.assertEqual(names, ["unit_template_runtime_request", "service_smoke_without_nested_full_suite"])
        smoke = payload["commands"][1]
        self.assertEqual(smoke["env"]["SPATIAL_AGENT_SMOKE_NESTED"], "1")

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


if __name__ == "__main__":
    unittest.main()
