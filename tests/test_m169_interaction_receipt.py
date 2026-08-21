"""M169: selection continuation has a SQLite CAS receipt."""

from pathlib import Path
import json
import tempfile
import unittest

from agent.artifact_store import ArtifactStore
from agent.contract_versions import (
    ACTION_ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_MIGRATION_SCHEMA_VERSION,
    RUN_ARTIFACT_SCHEMA_VERSION,
)
from agent.capability_catalog import capability_catalog
from agent.evidence_contract import build_capability_evidence
from agent.service import AgentService
from agent.workflow_selection import build_workflow_selection_evidence
from evaluation.model_evaluation import _build_recorded_runtime
from result_contract import build_result_contract
from tests.test_m166_multi_candidate_selection import AmbiguousTextDomainPack


class M169InteractionReceiptTests(unittest.TestCase):
    def _service(self, root: Path) -> AgentService:
        return AgentService(
            state_db_path=str(root / "state.db"),
            artifact_store=ArtifactStore(root / "artifacts"),
            domain_pack=AmbiguousTextDomainPack(),
        )

    def test_memory_demo_is_not_reported_as_real_data_unavailable(self):
        catalog = capability_catalog(environment="memory")
        capability = next(
            item
            for item in catalog["capabilities"]
            if item["id"] == "spatial_analysis"
        )
        self.assertTrue(capability["available"])
        self.assertEqual(capability["availability_mode"], "demo")
        evidence = build_capability_evidence(capability)
        self.assertEqual(evidence["status"], "degraded")
        self.assertEqual(evidence["availability"]["mode"], "demo")
        selection = build_workflow_selection_evidence(
            discovery={"candidate_ids": ["spatial_analysis"]},
            domain_id="gis",
            capability_catalog=catalog,
        )
        candidate = selection["candidate_details"][0]
        self.assertEqual(candidate["data"]["availability_mode"], "demo")
        self.assertEqual(candidate["evidence"]["availability"]["mode"], "demo")

    def test_duplicate_capability_choice_replays_same_child_run(self):
        with tempfile.TemporaryDirectory(prefix="m169-receipt-") as directory:
            root = Path(directory)
            service = self._service(root)
            try:
                pending = service.run(
                    request="请处理这段内容",
                    session_id="m169-choice",
                    planner="rule",
                    backend="memory",
                )
                first = service.apply_run_interaction(
                    pending["run_id"],
                    "select_capability",
                    {
                        "capability_id": "text_summary",
                        "require_confirmation": False,
                        "export_artifact": True,
                        "idempotency_key": "m169-choice-1",
                    },
                )
                artifact = json.loads(
                    Path(first["artifact_ref"]).read_text(encoding="utf-8")
                )
                replay = service.apply_run_interaction(
                    pending["run_id"],
                    "select_capability",
                    {
                        "capability_id": "text_summary",
                        "require_confirmation": False,
                        "export_artifact": True,
                        "idempotency_key": "m169-choice-1",
                    },
                )
            finally:
                service.close()

        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertTrue(replay["interaction_receipt"]["reused"])
        self.assertEqual(
            artifact["interaction_receipt"]["schema_version"],
            "spatial-agent.interaction-receipt.v1",
        )
        self.assertEqual(
            replay["interaction_receipt"]["schema_version"],
            "spatial-agent.interaction-receipt.v1",
        )

    def test_source_run_action_is_compare_and_swap_boundary(self):
        with tempfile.TemporaryDirectory(prefix="m169-cas-") as directory:
            root = Path(directory)
            service = self._service(root)
            try:
                pending = service.run(
                    request="请处理这段内容",
                    session_id="m169-cas",
                    planner="rule",
                    backend="memory",
                )
                service.apply_run_interaction(
                    pending["run_id"],
                    "select_capability",
                    {
                        "capability_id": "text_summary",
                        "require_confirmation": False,
                        "idempotency_key": "m169-cas-1",
                    },
                )
                with self.assertRaisesRegex(ValueError, "conflicts"):
                    service.apply_run_interaction(
                        pending["run_id"],
                        "select_capability",
                        {
                            "capability_id": "text_summary",
                            "require_confirmation": True,
                            "idempotency_key": "m169-cas-2",
                        },
                    )
            finally:
                service.close()

    def test_receipt_replays_after_service_restart(self):
        with tempfile.TemporaryDirectory(prefix="m169-restart-") as directory:
            root = Path(directory)
            service = self._service(root)
            try:
                pending = service.run(
                    request="请处理这段内容",
                    session_id="m169-restart",
                    planner="rule",
                    backend="memory",
                )
                first = service.apply_run_interaction(
                    pending["run_id"],
                    "select_capability",
                    {
                        "capability_id": "text_summary",
                        "require_confirmation": False,
                        "export_artifact": True,
                        "idempotency_key": "m169-restart-1",
                    },
                )
            finally:
                service.close()

            restarted = self._service(root)
            try:
                replay = restarted.apply_run_interaction(
                    pending["run_id"],
                    "select_capability",
                    {
                        "capability_id": "text_summary",
                        "require_confirmation": False,
                        "export_artifact": True,
                        "idempotency_key": "m169-restart-1",
                    },
                )
            finally:
                restarted.close()

        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertTrue(replay["interaction_receipt"]["reused"])

    def test_legacy_run_has_explicit_bounded_migration(self):
        with tempfile.TemporaryDirectory(prefix="m169-migration-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            legacy = root / "artifacts" / "legacy.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                json.dumps(
                    {
                        "run_id": "legacy",
                        "domain_id": "text",
                        "status": "COMPLETED",
                        "request": "旧版本摘要",
                        "result_type": "text_summary_result",
                    }
                ),
                encoding="utf-8",
            )

            readable = store.read_run("legacy", domain_id="text")
            migrated_ref = store.migrate_run("legacy", domain_id="text")
            migrated = store.read_run("legacy", domain_id="text")

        self.assertNotIn("artifact_schema_version", readable)
        self.assertTrue(migrated_ref)
        self.assertEqual(migrated["artifact_schema_version"], RUN_ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(
            migrated["artifact_migration"]["schema_version"],
            ARTIFACT_MIGRATION_SCHEMA_VERSION,
        )
        self.assertEqual(
            migrated["artifact_migration"]["source_schema_version"],
            "legacy-unversioned",
        )

    def test_unknown_artifact_versions_are_not_migrated_or_replayed(self):
        with tempfile.TemporaryDirectory(prefix="m169-future-artifact-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            (root / "artifacts").mkdir(parents=True)
            (root / "artifacts" / "future.json").write_text(
                json.dumps(
                    {
                        "run_id": "future",
                        "domain_id": "text",
                        "artifact_schema_version": "spatial-agent.run-artifact.v9",
                    }
                ),
                encoding="utf-8",
            )
            (root / "artifacts" / "action-future.json").write_text(
                json.dumps(
                    {
                        "action_execution_id": "future",
                        "domain_id": "text",
                        "artifact_schema_version": "spatial-agent.action-artifact.v9",
                    }
                ),
                encoding="utf-8",
            )

            self.assertIsNone(store.read_run("future", domain_id="text"))
            self.assertIsNone(store.migrate_run("future", domain_id="text"))
            self.assertIsNone(store.read_action("future", domain_id="text"))

        self.assertEqual(ACTION_ARTIFACT_SCHEMA_VERSION, "spatial-agent.action-artifact.v1")

    def test_model_capability_disagreement_is_versioned_evidence(self):
        runtime = _build_recorded_runtime(
            {
                "goal": "错误地查询行政区",
                "steps": [
                    {
                        "id": "schema",
                        "tool": "get_dataset_schema",
                        "args": {"dataset": "admin_areas"},
                        "depends_on": [],
                    },
                    {
                        "id": "query",
                        "tool": "range_query",
                        "args": {"dataset": "admin_areas", "conditions": [], "limit": 100},
                        "depends_on": ["schema"],
                    },
                ],
                "output": {"type": "admin_area_result", "summary": True},
            },
            {"provider": "offline-selection-replay", "status": "success"},
        )
        result = runtime.run("查询DEM栅格元数据")
        alignment = (result.plan_evidence or {}).get("planner_selection") or {}

        self.assertEqual(alignment["schema_version"], "spatial-agent.planner-selection.v1")
        self.assertEqual(alignment["state"], "mismatch")
        self.assertEqual(alignment["selected_capability_id"], "raster_metadata")
        self.assertEqual(alignment["planner_capability_id"], "admin_boundary_query")

    def test_failed_bounded_plan_repair_keeps_repair_lineage(self):
        invalid = {
            "goal": "无效摘要计划",
            "steps": [
                {
                    "id": "summary",
                    "tool": "summarize_text",
                    "args": {"text": "repair failure"},
                    "depends_on": ["missing"],
                }
            ],
            "output": {"type": "text_summary_result"},
        }
        runtime = _build_recorded_runtime(
            [invalid, invalid],
            {"provider": "offline-repair-failure", "status": "success"},
            domain="text",
        )
        result = runtime.run("请摘要这段文本")
        payload = result.to_dict()
        contract = build_result_contract(payload)
        events = contract["replanning"]["events"]

        self.assertEqual(result.status.value, "FAILED")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["phase"], "planning")
        self.assertEqual(events[0]["repair_status"], "failed")
        self.assertEqual(events[0]["repair_reason_code"], "replacement_invalid")
        self.assertEqual(events[0]["replanned_step_ids"], [])


if __name__ == "__main__":
    unittest.main()
