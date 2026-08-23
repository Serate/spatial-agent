import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from run_demo import build_runtime


ROOT = Path(__file__).parents[1]
HAS_GIS = importlib.util.find_spec("geopandas") is not None
HAS_LOCAL_DATA = Path("D:/dataset/agent/\u6e56\u5317\u7701_\u53bf.geojson").exists()
GENERIC_ADMIN_QUERY = "\u67e5\u8be2\u884c\u653f\u533a\u8fb9\u754c"
ADMIN_NAME = "\u6d2a\u5c71\u533a"


class M9ClarificationLoopTests(unittest.TestCase):
    def test_runtime_continues_after_admin_name_clarification(self):
        runtime = build_runtime("rule")

        first = runtime.run(GENERIC_ADMIN_QUERY, session_id="m9-admin")
        self.assertEqual(first.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(first.clarification["state"], "capability_facts_required")
        self.assertTrue(first.clarification["missing_fields"])

        second = runtime.run(ADMIN_NAME, session_id="m9-admin")
        self.assertEqual(second.status.value, "COMPLETED")
        self.assertEqual(second.plan.goal, "query admin area boundary by name")
        self.assertEqual(second.steps[1].args["conditions"][0]["value"], ADMIN_NAME)
        self.assertIn("memory://range/admin_areas", second.answer)
        self.assertIn(GENERIC_ADMIN_QUERY, second.resolved_request)

    def test_pending_clarification_is_scoped_by_session(self):
        runtime = build_runtime("rule")
        runtime.run(GENERIC_ADMIN_QUERY, session_id="one")

        result = runtime.run(ADMIN_NAME, session_id="two")
        self.assertEqual(result.status.value, "NEEDS_CLARIFICATION")
        self.assertIn("road condition", result.error)

    def test_completed_follow_up_clears_pending_request(self):
        runtime = build_runtime("rule")
        runtime.run(GENERIC_ADMIN_QUERY, session_id="m9-clear")
        completed = runtime.run(ADMIN_NAME, session_id="m9-clear")
        self.assertEqual(completed.status.value, "COMPLETED")

        next_result = runtime.run(ADMIN_NAME, session_id="m9-clear")
        self.assertEqual(next_result.status.value, "NEEDS_CLARIFICATION")

    def test_demo_cli_runs_follow_up_turns_in_one_session(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "run_demo.py"),
                GENERIC_ADMIN_QUERY,
                "--follow-up",
                ADMIN_NAME,
                "--session-id",
                "m9-cli",
            ],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload[0]["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(payload[1]["status"], "COMPLETED")
        self.assertIn("memory://range/admin_areas", payload[1]["answer"])


@unittest.skipUnless(HAS_GIS and HAS_LOCAL_DATA, "requires geopandas and local admin GeoJSON")
class M9ClarificationLoopLocalBackendTests(unittest.TestCase):
    def test_local_backend_continues_after_admin_name_clarification(self):
        runtime = build_runtime("rule", "local")
        first = runtime.run(GENERIC_ADMIN_QUERY, session_id="m9-local")
        self.assertEqual(first.status.value, "NEEDS_CLARIFICATION")

        second = runtime.run(ADMIN_NAME, session_id="m9-local")
        self.assertEqual(second.status.value, "COMPLETED")
        self.assertIn("geojson://range/admin_areas", second.answer)
        self.assertIn("EPSG:4490", second.answer)


if __name__ == "__main__":
    unittest.main()
