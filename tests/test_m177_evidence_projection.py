"""M177: one bounded evidence projection serves async and artifact surfaces."""

from copy import deepcopy
import unittest

from agent.artifact_viewer import render_artifact_html
from agent.evidence_projection import (
    EVIDENCE_MIGRATION_SCHEMA_VERSION,
    EVIDENCE_PROJECTION_SCHEMA_VERSION,
    project_evidence_projection,
)
from agent.service_async import build_async_result_evidence
from result_contract import build_result_contract


def _payload():
    return {
        "run_id": "m177-run",
        "domain_id": "text",
        "status": "COMPLETED",
        "answer": "已完成。",
        "result_type": "text_summary_result",
        "plan": {"goal": "摘要文本", "steps": [], "output": {"type": "text_summary_result"}},
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


class M177EvidenceProjectionTests(unittest.TestCase):
    def test_current_projection_is_shared_by_async_and_artifact_viewer(self):
        payload = _payload()
        contract = build_result_contract(payload)
        full = {**payload, "result": contract}
        projection = project_evidence_projection(full)
        async_evidence = build_async_result_evidence(contract, status="COMPLETED")

        self.assertEqual(projection["schema_version"], EVIDENCE_PROJECTION_SCHEMA_VERSION)
        self.assertEqual(projection["migration"]["schema_version"], EVIDENCE_MIGRATION_SCHEMA_VERSION)
        self.assertEqual(projection["migration"]["state"], "current")
        self.assertEqual(projection["selection"]["planner_selection"]["state"], "matched")
        self.assertEqual(
            async_evidence["evidence_projection"]["selection"], projection["selection"]
        )

        html = render_artifact_html(full)
        self.assertIn("证据索引（Evidence Registry）", html)
        self.assertIn("工作流选择", html)
        self.assertIn("规划器选择", html)
        self.assertIn("text_summary_result", html)

    def test_legacy_incomplete_registry_is_explicitly_migratable(self):
        payload = _payload()
        contract = build_result_contract(payload)
        legacy = deepcopy(contract["evidence_registry"])
        legacy["entries"] = [
            item for item in legacy["entries"]
            if item["id"] not in {"workflow_selection", "planner_selection"}
        ]
        legacy["entry_count"] = len(legacy["entries"])
        projection = project_evidence_projection(
            {**payload, "result": {**contract, "evidence_registry": legacy}}
        )
        self.assertEqual(projection["migration"]["state"], "legacy_incomplete")
        self.assertTrue(projection["migration"]["migratable"])
        self.assertEqual(projection["migration"]["action"], "rebuild_from_result")
        self.assertFalse(projection["evidence_registry_completeness"]["passed"])


if __name__ == "__main__":
    unittest.main()
