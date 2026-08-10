import tempfile
import time
import unittest
from pathlib import Path

from agent.service import AgentService


class M69WorkflowRuntimeTests(unittest.TestCase):
    def test_selected_constraints_change_the_rule_plan_and_are_returned(self):
        result = AgentService().run(
            "查询栅格元数据",
            session_id="workflow-runtime",
            workflow={
                "template_id": "raster_metadata",
                "constraints": {"dataset": "land_use"},
                "evidence": ["summary", "metadata"],
            },
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["workflow"]["template_version"], "1.0.0")
        self.assertEqual(result["workflow"]["constraints"]["dataset"], "land_use")
        self.assertEqual(result["plan"]["steps"][0]["args"]["dataset"], "land_use")

    def test_workflow_survives_sqlite_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state_db = str(Path(directory) / "agent.db")
            workflow = {
                "template_id": "raster_metadata",
                "constraints": {"dataset": "dem"},
                "evidence": ["summary", "metadata"],
            }
            first = AgentService(state_db_path=state_db).run(
                "查询栅格元数据", session_id="restart-workflow", workflow=workflow
            )
            restored = AgentService(state_db_path=state_db).get_run(first["run_id"])

        self.assertEqual(restored["workflow"], first["workflow"])
        self.assertEqual(restored["plan"]["steps"][0]["args"]["dataset"], "dem")

    def test_async_submission_persists_normalized_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "agent.db"))
            submitted = service.run_async(
                request="查询栅格元数据",
                session_id="async-workflow",
                workflow={
                    "template_id": "raster_metadata",
                    "constraints": {"dataset": "dem"},
                    "evidence": ["summary", "metadata"],
                },
            )
            result = None
            for _ in range(100):
                result = service.get_run(submitted["run_id"])
                if result["status"] not in {"PLANNING", "EXECUTING"}:
                    break
                time.sleep(0.01)

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["workflow"]["constraints"]["dataset"], "dem")

    def test_plan_is_rejected_when_selected_template_does_not_allow_it(self):
        result = AgentService().run(
            "查询 DEM 栅格元数据",
            workflow={
                "template_id": "admin_boundary_query",
                "constraints": {"admin_name": "洪山区"},
                "evidence": ["summary", "geometry", "trace"],
            },
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("tool is not allowed by template", result["error"])
        self.assertEqual(result["workflow"]["template_id"], "admin_boundary_query")


if __name__ == "__main__":
    unittest.main()
