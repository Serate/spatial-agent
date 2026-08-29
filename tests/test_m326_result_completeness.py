"""Compact M326 coverage for the shared completion projection."""

import unittest

from agent.application.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from agent.evidence_projection import project_evidence_projection
from agent.persistence.artifact_manifest import build_artifact_manifest
from agent.result_completeness import build_result_completeness
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.runtime_core.projection import append_execution_degradation_notice
from result_contract import build_result_contract


def _partial_payload():
    return {
        "run_id": "m326-partial",
        "status": "COMPLETED",
        "request": "执行开放式分析",
        "answer": "已根据已完成证据生成部分结论。",
        "react_evidence": {
            "schema_version": "spatial-agent.react-evidence.v1",
            "state": "partial",
            "action_count": 2,
            "reason_code": "react_action_validation_recovery_finish",
            "turns": [],
        },
        "plan": {
            "goal": "执行开放式分析",
            "steps": [{"id": "react-1", "tool": "registered_tool", "args": {}}],
            "output": {"type": "direct_answer"},
        },
        "steps": [
            {
                "id": "react-1",
                "tool": "registered_tool",
                "status": "COMPLETED",
                "result": {"result_type": "direct_answer"},
            }
        ],
    }


class M326ResultCompletenessTests(unittest.TestCase):
    def test_partial_state_is_bounded_and_preserves_stop_reason(self):
        completeness = build_result_completeness(_partial_payload())

        self.assertEqual(completeness["state"], "partial")
        self.assertEqual(completeness["attempted_action_count"], 2)
        self.assertEqual(completeness["planned_action_count"], 2)
        self.assertEqual(completeness["completed_action_count"], 1)
        self.assertEqual(
            completeness["stop_reason"],
            "react_action_validation_recovery_finish",
        )
        self.assertTrue(completeness["retryable"])
        self.assertNotIn("error", str(completeness))

    def test_result_and_async_evidence_share_completion_projection(self):
        payload = _partial_payload()
        contract = build_result_contract(payload)
        self.assertEqual(contract["completeness"]["state"], "partial")

        async_evidence = build_async_result_evidence(
            contract,
            status="COMPLETED",
            artifact_ref="run-m326-partial.json",
        )
        self.assertEqual(async_evidence["completeness"], contract["completeness"])
        restored = normalize_async_result_evidence(
            async_evidence,
            status="COMPLETED",
            artifact_ref="run-m326-partial.json",
        )
        self.assertEqual(restored["completeness"], contract["completeness"])

        shared = project_evidence_projection({"result": contract})
        self.assertEqual(shared["completeness"], contract["completeness"])
        manifest = build_artifact_manifest(
            {"run_id": "m326-partial", "status": "COMPLETED", "result": contract}
        )
        self.assertEqual(manifest["completeness"], contract["completeness"])

    def test_terminal_states_are_not_collapsed_into_success(self):
        waiting = build_result_completeness(
            {
                "status": "WAITING_FOR_DECISION",
                "react_evidence": {"state": "awaiting_approval", "action_count": 1},
            }
        )
        blocked = build_result_completeness(
            {
                "status": "FAILED",
                "react_evidence": {
                    "state": "blocked",
                    "action_count": 1,
                    "reason_code": "tool_arguments_invalid",
                },
                "failure": {"code": "tool_arguments_invalid", "retryable": False},
            }
        )
        pending = build_result_completeness({"status": "EXECUTING"})

        self.assertEqual(waiting["state"], "waiting_decision")
        self.assertEqual(waiting["stop_reason"], "decision_required")
        self.assertEqual(blocked["state"], "blocked")
        self.assertFalse(blocked["retryable"])
        self.assertEqual(pending["state"], "pending")

    def test_composite_partial_and_answer_notice_remain_partial(self):
        composite = build_result_completeness(
            {"status": "COMPLETED", "composite": {"state": "partial"}}
        )
        result = AgentRunResult(
            run_id="m326-answer",
            status=RunStatus.COMPLETED,
            request="开放式分析",
            plan=TaskPlan(
                goal="开放式分析",
                steps=[PlanStep("step-1", "tool", {})],
                output={"type": "text_summary_result"},
            ),
            react_evidence={
                "schema_version": "spatial-agent.react-evidence.v1",
                "state": "partial",
                "action_count": 2,
                "reason_code": "react_action_validation_recovery_finish",
                "turns": [],
            },
            steps=[StepRun("step-1", "tool", {}, status="COMPLETED")],
        )

        answer = append_execution_degradation_notice(result, "已整理当前结果。")

        self.assertEqual(composite["state"], "partial")
        self.assertIn("只完成了部分分析", answer)
        self.assertIn("未完成部分的结果未知", answer)

    def test_completed_parent_does_not_hide_partial_composite_children(self):
        from agent.application.composite_contract import build_composite_result_contract
        from tests.test_m275_composite_contract import _children, _request

        request = _request()
        request["components"][1]["required"] = False
        children = _children()
        children["economy"]["status"] = "FAILED"
        result = build_composite_result_contract(request, children)

        self.assertEqual(result["completeness"]["state"], "partial")


if __name__ == "__main__":
    unittest.main()
