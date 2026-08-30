"""Compact M331-D contracts for answer quality and live event visibility."""

from __future__ import annotations

import unittest

from agent.answer_generation import LLMAnswerGenerator
from agent.answer_quality import assess_answer
from agent.models import AgentRunResult, RunStatus, TaskPlan
from agent.run_events import new_run_event


def _result(status: RunStatus = RunStatus.COMPLETED) -> AgentRunResult:
    return AgentRunResult(
        run_id="m331-answer",
        status=status,
        request="请总结结果",
        plan=TaskPlan("总结结果", [], {"type": "direct_answer"}),
    )


class _Client:
    def complete_json(self, _messages, _schema):
        return {"answer": "结论：这是一段面向普通用户的自然中文说明。"}

    def metrics(self):
        return {"execution_mode": "live_model", "status": "success"}


class M331AnswerExperienceTests(unittest.TestCase):
    def test_completed_answer_quality_is_pass_without_domain_rules(self):
        quality = assess_answer(
            "结论：结果已整理，详细说明和限制已列在下方。",
            {"status": "COMPLETED", "completeness": {"state": "complete"}},
        )
        self.assertEqual(quality["status"], "pass")
        self.assertTrue(quality["checks"]["state_disclosed"])

    def test_partial_and_waiting_answers_must_disclose_state(self):
        partial = assess_answer("结论已生成。", {"completeness": {"state": "partial"}})
        waiting = assess_answer("请确认后继续。", {"state": "waiting_decision"})
        self.assertEqual(partial["status"], "warn")
        self.assertIn("answer_state_not_disclosed", partial["reason_codes"])
        self.assertEqual(waiting["status"], "pass")

    def test_quality_rejects_internal_or_garbled_visible_text(self):
        quality = assess_answer("[object Object] memory://private \ufffd")
        self.assertEqual(quality["status"], "fail")
        self.assertIn("answer_internal_marker", quality["reason_codes"])
        self.assertIn("answer_unreadable", quality["reason_codes"])

    def test_live_answer_evidence_contains_quality_receipt(self):
        generated = LLMAnswerGenerator(_Client()).generate(_result())
        self.assertEqual(generated.evidence["quality"]["schema_version"], "spatial-agent.answer-quality.v1")
        self.assertEqual(generated.evidence["quality"]["status"], "pass")

    def test_react_approval_event_is_part_of_shared_event_contract(self):
        event = new_run_event(
            run_id="m331-answer",
            phase="execute",
            kind="react_waiting_for_approval",
            status="WAITING_FOR_DECISION",
            message="工具提案已验证，等待人工审批",
        )
        self.assertEqual(event["kind"], "react_waiting_for_approval")


if __name__ == "__main__":
    unittest.main()
