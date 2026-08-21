"""M173: selection and repair evidence remain comparable across entries."""

from __future__ import annotations

import copy
import unittest

from agent.planner_selection import PLANNER_SELECTION_SCHEMA_VERSION
from agent.runtime_factory import build_runtime
from agent.service import AgentService
from evaluation.contract_harness import compare_results, normalize_result
from evaluation.model_evaluation import _build_recorded_runtime
from result_contract import build_result_contract
from tests.test_m166_multi_candidate_selection import AmbiguousTextDomainPack


def _payload(*, selection=None, replan_events=None):
    plan_evidence = {
        "available": True,
        "planner_kind": "LLMPlanner",
        "source": "domain_discovery",
        "selected_capability_id": "raster_metadata",
        "capability_candidate_ids": ["raster_metadata"],
        "planner_selection": selection
        or {
            "schema_version": PLANNER_SELECTION_SCHEMA_VERSION,
            "state": "matched",
            "reason_code": "planner_matches_selected_capability",
            "result_type": "raster_metadata_result",
            "selected_capability_id": "raster_metadata",
            "planner_capability_id": "raster_metadata",
            "planner_kind": "LLMPlanner",
            "candidate_ids": ["raster_metadata"],
        },
    }
    payload = {
        "run_id": "m173-run",
        "domain_id": "gis",
        "status": "COMPLETED",
        "request": "查询 DEM 栅格元数据",
        "answer": "已完成。",
        "plan": {
            "goal": "查询栅格元数据",
            "steps": [],
            "output": {"type": "raster_metadata_result"},
        },
        "steps": [],
        "plan_evidence": plan_evidence,
        "replan_events": replan_events or [],
        "result_type": "raster_metadata_result",
    }
    payload["result"] = build_result_contract(payload)
    return payload


class M173SelectionContractTests(unittest.TestCase):
    def test_harness_compares_model_selection_evidence(self):
        first = _payload()
        second = copy.deepcopy(first)
        second["result"]["planning"]["planner_selection"]["state"] = "mismatch"
        second["result"]["planning"]["planner_selection"]["reason_code"] = (
            "planner_differs_from_selected_capability"
        )
        differences = compare_results([first, second])
        self.assertTrue(
            any("$.planner_selection.state" in item for item in differences),
            differences,
        )

    def test_repair_lineage_ignores_timing_but_detects_semantic_drift(self):
        event = {
            "failed_step_id": "plan-validation",
            "failed_tool": "planner",
            "failure_category": "tool_validation",
            "phase": "planning",
            "repair_status": "repaired",
            "repair_reason_code": "replacement_valid",
            "replanned_step_ids": ["summary"],
            "latency_ms": 12.5,
            "occurred_at": 100.0,
        }
        first = _payload(replan_events=[event])
        second = copy.deepcopy(first)
        second["result"]["replanning"]["events"][0]["latency_ms"] = 999.0
        second["result"]["replanning"]["events"][0]["occurred_at"] = 200.0
        self.assertEqual(compare_results([first, second]), [])

        second["result"]["replanning"]["events"][0]["repair_status"] = "failed"
        differences = compare_results([first, second])
        self.assertTrue(
            any("$.repair_lineage.events" in item for item in differences),
            differences,
        )

    def test_normalized_contract_exposes_unresolved_selection_safely(self):
        unresolved = {
            "schema_version": PLANNER_SELECTION_SCHEMA_VERSION,
            "state": "unresolved",
            "reason_code": "planner_result_type_not_bound_to_candidate",
            "result_type": "unknown_result",
            "selected_capability_id": "raster_metadata",
            "planner_capability_id": None,
            "planner_kind": "LLMPlanner",
            "candidate_ids": ["raster_metadata"],
        }
        projection = normalize_result(_payload(selection=unresolved)).as_dict()
        self.assertEqual(
            projection["planner_selection"]["state"],
            "unresolved",
        )
        self.assertEqual(
            projection["planner_selection"]["selected_capability_id"],
            "raster_metadata",
        )

    def test_recorded_model_and_rule_share_capability_selection_semantics(self):
        response = {
            "goal": "inspect raster metadata",
            "steps": [
                {
                    "id": "metadata",
                    "tool": "get_raster_metadata",
                    "args": {"dataset": "dem", "max_files": 3},
                    "depends_on": [],
                }
            ],
            "output": {"type": "raster_metadata_result", "summary": True},
        }
        replay_runtime = _build_recorded_runtime(
            response,
            {"usage": {"total_tokens": 88}, "latency_ms": 20},
        )
        model_result = replay_runtime.run("查询 DEM 栅格元数据")
        rule_result = build_runtime("rule", "memory").run("查询 DEM 栅格元数据")

        model_selection = model_result.plan_evidence["planner_selection"]
        rule_selection = rule_result.plan_evidence["planner_selection"]
        self.assertEqual(model_selection["selected_capability_id"], "raster_metadata")
        self.assertEqual(rule_selection["selected_capability_id"], "raster_metadata")
        self.assertEqual(model_selection["state"], rule_selection["state"])
        self.assertNotEqual(model_selection["planner_kind"], rule_selection["planner_kind"])

    def test_ambiguous_domain_stays_structured_before_any_tool_execution(self):
        service = AgentService(domain_pack=AmbiguousTextDomainPack())
        try:
            payload = service.run(
                "请处理这段内容",
                session_id="m173-ambiguous",
                planner="rule",
                backend="memory",
            )
        finally:
            service.close()

        selection = payload["result"]["planning"]["workflow_selection"]
        self.assertEqual(payload["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(selection["state"], "ambiguous")
        self.assertEqual(payload["steps"], [])


if __name__ == "__main__":
    unittest.main()
