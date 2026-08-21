"""M175: selection evidence is a first-class Evidence Registry entry."""

from copy import deepcopy
import unittest

from agent.evidence_registry import project_evidence_registry_completeness
from evaluation.contract_harness import compare_results, normalize_result
from result_contract import build_result_contract


def _payload(domain_id="text"):
    return {
        "run_id": "m175-run",
        "domain_id": domain_id,
        "status": "COMPLETED",
        "answer": "已完成。",
        "plan": {
            "goal": "摘要文本",
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
                "domain_id": domain_id,
                "source": "domain_discovery",
                "selected_capability_id": "text_summary",
                "candidate_ids": ["text_summary"],
                "candidate_count": 1,
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
        "result_type": "text_summary_result",
    }


class M175SelectionRegistryTests(unittest.TestCase):
    def test_text_and_gis_registry_share_selection_entries(self):
        text = _payload("text")
        gis = _payload("gis")
        text["result"] = build_result_contract(text)
        gis["result"] = build_result_contract(gis)

        expected = {
            "result",
            "plan_quality",
            "execution_timeline",
            "action_lifecycle",
            "replanning",
            "workflow_selection",
            "planner_selection",
        }
        for payload in (text, gis):
            ids = {item["id"] for item in payload["result"]["evidence_registry"]["entries"]}
            self.assertTrue(expected.issubset(ids), ids)
            check = project_evidence_registry_completeness(
                payload["result"]["evidence_registry"]
            )
            self.assertTrue(check["passed"], check)
        self.assertEqual(
            normalize_result(text).as_dict()["evidence_registry"],
            normalize_result(gis).as_dict()["evidence_registry"],
        )

    def test_missing_planner_selection_entry_fails_current_completeness(self):
        payload = _payload()
        payload["result"] = build_result_contract(payload)
        registry = deepcopy(payload["result"]["evidence_registry"])
        registry["entries"] = [
            item for item in registry["entries"] if item["id"] != "planner_selection"
        ]
        registry["entry_count"] = len(registry["entries"])
        check = project_evidence_registry_completeness(registry)
        self.assertFalse(check["passed"])
        self.assertIn("planner_selection", check["missing_entry_ids"])

    def test_cross_entry_harness_detects_selection_registry_loss(self):
        first = _payload()
        second = deepcopy(first)
        first["result"] = build_result_contract(first)
        second["result"] = build_result_contract(second)
        second["result"]["evidence_registry"]["entries"] = [
            item
            for item in second["result"]["evidence_registry"]["entries"]
            if item["id"] != "workflow_selection"
        ]
        second["result"]["evidence_registry"]["entry_count"] = len(
            second["result"]["evidence_registry"]["entries"]
        )
        differences = compare_results([first, second])
        self.assertTrue(
            any("$.evidence_registry" in item for item in differences),
            differences,
        )


if __name__ == "__main__":
    unittest.main()
