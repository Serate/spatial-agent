"""M176: async polling preserves the same selection evidence projection."""

import unittest
from pathlib import Path

from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from result_contract import build_result_contract


def _payload():
    return {
        "run_id": "m176-run",
        "domain_id": "text",
        "status": "COMPLETED",
        "answer": "已完成。",
        "result_type": "text_summary_result",
        "plan": {"output": {"type": "text_summary_result"}, "steps": []},
        "steps": [],
        "plan_evidence": {
            "available": True,
            "workflow_selection": {
                "schema_version": "spatial-agent.workflow-selection.v1",
                "state": "selected",
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


class M176SelectionFrontendContractTests(unittest.TestCase):
    def test_console_uses_shared_renderer_and_both_http_entries_allow_asset(self):
        root = Path(__file__).parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="./console_evidence_registry.js"', html)
        self.assertIn('id="selectionEvidence"', html)
        self.assertIn("ConsoleEvidenceRegistry", html)
        self.assertIn("selectionEvidence", html)
        self.assertIn("render(planEvidence,evidenceRegistry,evidenceRecovery)", html)
        self.assertIn("renderCompact(evidence.planning,evidence.evidence_registry,evidence.evidence_recovery)", html)
        self.assertIn('data-evidence-recovery-state="recoverable"', html)
        for entry in (root / "serve_api.py", root / "production_api.py"):
            self.assertIn("console_evidence_registry.js", entry.read_text(encoding="utf-8"))

    def test_async_projection_keeps_workflow_and_planner_selection(self):
        payload = _payload()
        contract = build_result_contract(payload)
        evidence = normalize_async_result_evidence(
            build_async_result_evidence(contract, status="COMPLETED"),
            status="COMPLETED",
        )
        planning = evidence["planning"]
        self.assertEqual(planning["workflow_selection"]["state"], "selected")
        self.assertEqual(planning["planner_selection"]["state"], "matched")
        self.assertEqual(
            planning["planner_selection"]["result_type"], "text_summary_result"
        )
        self.assertEqual(evidence["evidence_registry"], contract["evidence_registry"])

    def test_legacy_async_projection_degrades_without_selection_payload(self):
        contract = build_result_contract({
            "status": "COMPLETED",
            "result_type": "text_summary_result",
            "plan": {"output": {"type": "text_summary_result"}, "steps": []},
            "steps": [],
        })
        evidence = build_async_result_evidence(contract, status="COMPLETED")
        self.assertEqual(evidence["planning"]["planner_selection"]["state"], "unavailable")
        self.assertEqual(evidence["planning"]["workflow_selection"]["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
