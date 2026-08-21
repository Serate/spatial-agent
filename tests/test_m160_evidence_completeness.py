"""M160: the evidence registry has a strict, replayable completeness contract."""

import copy
import unittest
from pathlib import Path

from agent.evidence_registry import (
    EVIDENCE_COMPLETENESS_SCHEMA_VERSION,
    project_evidence_registry_completeness,
)
from agent.models import PlanStep, TaskPlan
from agent.workflow_templates import WorkflowTemplateError
from evaluation.contract_harness import compare_results, normalize_result
from evaluation.model_evaluation import evaluate_model_replay_suite_file
from result_contract import build_result_contract
from domains.gis.domain import GIS_DOMAIN_PACK


ROOT = Path(__file__).parents[1]


def _payload(domain_id="gis"):
    return {
        "run_id": "m160-run",
        "domain_id": domain_id,
        "status": "COMPLETED",
        "answer": "已完成。",
        "result_type": "generic_result",
        "plan": {"output": {"type": "generic_result"}, "steps": []},
        "steps": [],
        "plan_evidence": {"available": False},
    }


class M160EvidenceCompletenessTests(unittest.TestCase):
    def test_gis_and_text_registries_have_the_same_core_contract(self):
        gis = build_result_contract(_payload("gis"))
        text = build_result_contract(_payload("text"))
        gis_check = project_evidence_registry_completeness(gis["evidence_registry"])
        text_check = project_evidence_registry_completeness(text["evidence_registry"])
        self.assertEqual(gis_check["schema_version"], EVIDENCE_COMPLETENESS_SCHEMA_VERSION)
        self.assertTrue(gis_check["passed"])
        self.assertTrue(text_check["passed"])
        self.assertEqual(gis_check["required_entry_ids"], text_check["required_entry_ids"])

    def test_missing_or_duplicate_core_entry_fails_without_reading_payload(self):
        registry = build_result_contract(_payload())["evidence_registry"]
        missing = copy.deepcopy(registry)
        missing["entries"] = [item for item in missing["entries"] if item["id"] != "replanning"]
        missing["entry_count"] = len(missing["entries"])
        missing_check = project_evidence_registry_completeness(missing)
        self.assertFalse(missing_check["passed"])
        self.assertIn("replanning", missing_check["missing_entry_ids"])

        duplicate = copy.deepcopy(registry)
        duplicate["entries"].append(copy.deepcopy(duplicate["entries"][0]))
        duplicate["entry_count"] = len(duplicate["entries"])
        duplicate_check = project_evidence_registry_completeness(duplicate)
        self.assertFalse(duplicate_check["passed"])
        self.assertIn("result", duplicate_check["duplicate_entry_ids"])

    def test_replay_reports_registry_completeness_as_a_pass_condition(self):
        report = evaluate_model_replay_suite_file(
            ROOT / "tests" / "fixtures" / "m69_model_replay_suite.json"
        )
        self.assertTrue(report["evidence_registry_completeness"]["passed"])
        self.assertEqual(
            report["evidence_registry_completeness"]["failed_count"],
            0,
        )
        for item in report["results"]:
            self.assertTrue(item["evidence_registry_completeness"]["passed"])

    def test_contract_harness_compares_completeness_but_not_domain_payload(self):
        first = _payload("gis")
        first["result"] = build_result_contract(first)
        second = copy.deepcopy(first)
        self.assertEqual(compare_results([first, second]), [])
        projection = normalize_result(first).as_dict()
        self.assertTrue(projection["evidence_registry_completeness"]["passed"])

        second["result"]["evidence_registry"]["entries"] = second["result"]["evidence_registry"]["entries"][:-1]
        second["result"]["evidence_registry"]["entry_count"] -= 1
        differences = compare_results([first, second])
        self.assertTrue(
            any("evidence_registry_completeness" in item for item in differences),
            differences,
        )

    def test_domain_plan_policy_rejects_extra_tools_without_runtime_gis_rules(self):
        plan = TaskPlan(
            goal="筛选建设候选",
            steps=[
                PlanStep("health", "get_dataset_health_report", {"dataset": "all"}),
                PlanStep("schema", "get_dataset_schema", {"dataset": "admin_areas"}),
                PlanStep("query", "range_query", {"dataset": "admin_areas", "conditions": [], "limit": 10}),
                PlanStep(
                    "screen",
                    "get_zonal_constrained_buildability_analysis",
                    {
                        "admin_name": "洪山区",
                        "slope_limit_degrees": 20,
                        "road_distance_m": 1000,
                        "exclude_water": True,
                    },
                    ["health"],
                ),
            ],
            output={"type": "constrained_buildability_result"},
        )
        with self.assertRaises(WorkflowTemplateError) as error:
            GIS_DOMAIN_PACK.validate_plan(plan)
        self.assertIn("domain workflow policy", str(error.exception))


if __name__ == "__main__":
    unittest.main()
