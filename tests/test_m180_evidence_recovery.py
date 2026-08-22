"""M180: one bounded migration/recovery projection serves all surfaces."""

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.artifact_viewer import render_artifact_html
from agent.evidence_recovery import (
    EVIDENCE_RECOVERY_SCHEMA_VERSION,
    project_evidence_recovery,
)
from agent.service_async import build_async_result_evidence
from result_contract import build_result_contract


def _payload():
    return {
        "run_id": "m180-run",
        "domain_id": "text",
        "status": "COMPLETED",
        "answer": "已完成。",
        "plan": {
            "goal": "生成摘要",
            "steps": [],
            "output": {"type": "text_summary_result"},
        },
        "steps": [],
        "plan_evidence": {
            "available": True,
            "workflow_selection": {
                "schema_version": "spatial-agent.workflow-selection.v1",
                "state": "selected",
                "reason_code": "workflow_selected",
                "source": "domain_discovery",
                "selected_capability_id": "text_summary",
                "candidate_ids": ["text_summary"],
            },
            "planner_selection": {
                "schema_version": "spatial-agent.planner-selection.v1",
                "state": "matched",
                "reason_code": "planner_matches_selected_capability",
                "result_type": "text_summary_result",
                "selected_capability_id": "text_summary",
                "planner_capability_id": "text_summary",
                "planner_kind": "RuleBasedPlanner",
                "candidate_ids": ["text_summary"],
            },
        },
    }


def _contract():
    payload = _payload()
    return build_result_contract(payload)


class M180EvidenceRecoveryTests(unittest.TestCase):
    def test_current_evidence_is_ready_without_recovery_action(self):
        recovery = project_evidence_recovery({"result": _contract()})

        self.assertEqual(recovery["schema_version"], EVIDENCE_RECOVERY_SCHEMA_VERSION)
        self.assertEqual(recovery["state"], "ready")
        self.assertEqual(recovery["action"], "none")
        self.assertEqual(recovery["allowed_actions"], [])
        self.assertFalse(recovery["migratable"])

    def test_legacy_incomplete_evidence_is_recoverable(self):
        contract = _contract()
        legacy = deepcopy(contract["evidence_registry"])
        legacy["entries"] = [
            item
            for item in legacy["entries"]
            if item["id"] not in {"workflow_selection", "planner_selection"}
        ]
        legacy["entry_count"] = len(legacy["entries"])

        recovery = project_evidence_recovery(
            {"result": {**contract, "evidence_registry": legacy}}
        )

        self.assertEqual(recovery["state"], "recoverable")
        self.assertEqual(recovery["action"], "rebuild_from_result")
        self.assertEqual(recovery["allowed_actions"], ["rebuild_from_result"])
        self.assertTrue(recovery["migratable"])

    def test_unknown_schema_is_blocked_without_implicit_migration(self):
        contract = _contract()
        unknown = deepcopy(contract["evidence_registry"])
        unknown["schema_version"] = "spatial-agent.evidence-registry.v99"

        recovery = project_evidence_recovery(
            {"result": {**contract, "evidence_registry": unknown}}
        )

        self.assertEqual(recovery["state"], "blocked")
        self.assertEqual(recovery["action"], "reject_until_explicit_migration")
        self.assertFalse(recovery["migratable"])

    def test_async_and_artifact_viewer_use_the_same_recovery_projection(self):
        contract = _contract()
        recovery = project_evidence_recovery({"result": contract})
        async_evidence = build_async_result_evidence(contract, status="COMPLETED")

        self.assertEqual(async_evidence["evidence_recovery"], recovery)
        html = render_artifact_html({**_payload(), "result": contract})
        self.assertIn("恢复状态：可用", html)
        self.assertIn("允许动作：无", html)

    def test_explicit_artifact_migration_rebuilds_legacy_registry_from_result(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(directory, legacy_domain_id="text")
            contract = _contract()
            path = Path(store.write_run({**_payload(), "result": contract}))
            artifact = json.loads(path.read_text(encoding="utf-8"))
            legacy = deepcopy(artifact["evidence_registry"])
            legacy["entries"] = [
                item for item in legacy["entries"]
                if item["id"] not in {"workflow_selection", "planner_selection"}
            ]
            legacy["entry_count"] = len(legacy["entries"])
            artifact["evidence_registry"] = legacy
            artifact["result"]["evidence_registry"] = legacy
            path.write_text(json.dumps(artifact), encoding="utf-8")

            migrated_ref = store.migrate_run("m180-run", domain_id="text")
            self.assertIsNotNone(migrated_ref)
            migrated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                migrated["artifact_migration"]["mode"],
                "explicit_rewrite_with_evidence_rebuild",
            )
            recovery = project_evidence_recovery(migrated)
            self.assertEqual(recovery["state"], "ready")
            self.assertTrue(
                migrated["result"]["evidence_registry"]["entry_count"] >= 7
            )


if __name__ == "__main__":
    unittest.main()
