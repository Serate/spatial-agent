import unittest
import tempfile
from pathlib import Path

from agent.action_lineage import (
    ACTION_LINEAGE_SCHEMA_VERSION,
    append_action_lineage,
    normalize_action_lineage,
    project_action_lineage,
)
from agent.execution_timeline import build_execution_timeline, normalize_execution_timeline
from agent.artifact_store import ArtifactStore
from agent.recovery_action import project_action_receipt
from agent.service import AgentService


class M187ActionLineageTests(unittest.TestCase):
    def test_consecutive_receipts_form_bounded_lineage_and_timeline_projection(self):
        first = {"action_id": "approve", "status": "COMPLETED"}
        second = {"action_id": "retry", "status": "COMPLETED"}
        lineage = append_action_lineage(
            project_action_lineage([first]), second
        )
        self.assertEqual(lineage["schema_version"], ACTION_LINEAGE_SCHEMA_VERSION)
        self.assertEqual(lineage["event_count"], 2)
        self.assertEqual(
            [item["action_id"] for item in lineage["events"]],
            ["approve", "retry"],
        )

        receipt = project_action_receipt({
            "action_id": "retry",
            "status": "COMPLETED",
            "transition_lineage": lineage,
        })
        timeline = normalize_execution_timeline(
            build_execution_timeline({"action_receipt": receipt})
        )
        action = next(item for item in timeline["events"] if item["kind"] == "action")
        self.assertEqual(
            action["action_linkage"]["transition_lineage"]["event_count"],
            2,
        )

    def test_lineage_is_bounded_and_unknown_schema_is_unavailable(self):
        receipts = [
            {"action_id": "retry", "status": "COMPLETED"}
            for _ in range(32)
        ]
        lineage = project_action_lineage(receipts)
        self.assertEqual(lineage["event_count"], 16)
        self.assertEqual(
            normalize_action_lineage({"schema_version": "spatial-agent.action-lineage.v99"})[
                "reason_code"
            ],
            "action_lineage_unknown_schema",
        )

    def test_service_action_persists_lineage_to_detail_and_artifact(self):
        with tempfile.TemporaryDirectory(prefix="m187-lineage-") as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            service = AgentService(
                state_db_path=str(Path(directory) / "state.db"),
                artifact_store=store,
            )
            try:
                pending = service.run(
                    "查询DEM栅格元数据",
                    session_id="m187-service",
                    require_confirmation=True,
                    export_artifact=True,
                )
                response = service.cancel(
                    pending["run_id"], idempotency_key="m187-cancel"
                )
                detail = service.get_run(pending["run_id"])
                artifact = store.read_run(pending["run_id"], domain_id="gis")
            finally:
                service.close()
        self.assertEqual(
            response["action_receipt"]["transition_lineage"]["event_count"],
            1,
        )
        self.assertEqual(
            detail["action_receipt"]["transition_lineage"],
            response["action_receipt"]["transition_lineage"],
        )
        self.assertEqual(
            artifact["action_receipt"]["transition_lineage"],
            response["action_receipt"]["transition_lineage"],
        )

    def test_console_consumes_lineage_without_domain_specific_branch(self):
        source = Path("web/index.html").read_text(encoding="utf-8")
        self.assertIn("transition_lineage", source)
        self.assertIn("连续动作", source)


if __name__ == "__main__":
    unittest.main()
