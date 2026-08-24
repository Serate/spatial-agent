import unittest

from agent.action_effect import (
    ACTION_EFFECT_SCHEMA_VERSION,
    normalize_action_effect,
    project_action_effect,
)
from agent.execution_timeline import build_execution_timeline, normalize_execution_timeline
from agent.recovery_action import project_action_receipt
from agent.service_async import build_async_result_evidence, normalize_async_result_evidence
from evaluation.contract_harness import compare_action_effects
from result_contract import build_result_contract


class M188ActionEffectTests(unittest.TestCase):
    def test_completed_action_reports_state_change_and_result_reference(self):
        effect = project_action_effect({
            "status": "CANCELLED",
            "source_status": "RUNNING",
            "current_status": "CANCELLED",
            "action_receipt": {
                "action_id": "cancel",
                "status": "COMPLETED",
                "result_ref": {"kind": "run", "id": "run-1"},
            },
        })
        self.assertEqual(effect["schema_version"], ACTION_EFFECT_SCHEMA_VERSION)
        self.assertEqual(effect["state"], "completed")
        self.assertEqual(effect["impact"], "state_changed")
        self.assertTrue(effect["result_available"])

    def test_receipt_effect_is_canonical_across_result_timeline_and_async(self):
        canonical = project_action_effect({
            "status": "COMPLETED",
            "action_receipt": {
                "action_id": "approve",
                "status": "COMPLETED",
                "result_ref": {"kind": "run", "id": "child"},
            },
        })
        receipt = project_action_receipt({
            "action_id": "approve",
            "status": "COMPLETED",
            "effect": canonical,
        })
        payload = {
            "run_id": "m188-effect",
            "status": "COMPLETED",
            "result_type": "text_summary_result",
            "answer": "已完成",
            "plan": {"output": {"type": "text_summary_result"}},
            "steps": [],
            "action_receipt": receipt,
            "action_effect": {
                "schema_version": ACTION_EFFECT_SCHEMA_VERSION,
                "state": "failed",
                "impact": "none",
            },
        }
        contract = build_result_contract(payload)
        self.assertEqual(contract["action_effect"], canonical)
        timeline = normalize_execution_timeline(contract["execution_timeline"])
        action = next(item for item in timeline["events"] if item["kind"] == "action")
        self.assertEqual(action["action_linkage"]["effect"], canonical)
        async_evidence = normalize_async_result_evidence(
            build_async_result_evidence(contract, status="COMPLETED"),
            status="COMPLETED",
        )
        self.assertEqual(async_evidence["action_effect"], canonical)

    def test_unknown_effect_schema_degrades_without_copying_fields(self):
        effect = normalize_action_effect({
            "schema_version": "spatial-agent.action-effect.v99",
            "state": "completed",
            "impact": "state_changed",
            "private": "do not copy",
        })
        self.assertFalse(effect["available"])
        self.assertEqual(effect["state"], "unknown")
        self.assertNotIn("private", effect)

    def test_effect_with_no_result_is_explicitly_no_change(self):
        effect = project_action_effect({
            "status": "COMPLETED",
            "action_receipt": {"action_id": "reject", "status": "COMPLETED"},
        })
        self.assertEqual(effect["impact"], "no_change")
        self.assertFalse(effect["result_available"])

    def test_lineage_and_console_keep_effect_as_structured_evidence(self):
        from pathlib import Path

from tests.console_source import read_console_source

        source = read_console_source(Path(__file__).parents[1])
        self.assertIn("effect.impact", source)
        self.assertIn("结果已关联", source)

    def test_effect_contract_detects_impact_drift_across_entries(self):
        attached = project_action_effect({
            "status": "COMPLETED",
            "action_receipt": {
                "action_id": "approve",
                "status": "COMPLETED",
                "result_ref": {"kind": "run", "id": "child"},
            },
        })
        no_change = dict(attached)
        no_change["impact"] = "no_change"
        differences = compare_action_effects([
            {"action_effect": attached},
            {"action_effect": no_change},
        ])
        self.assertTrue(any(item.endswith(".impact") for item in differences))


if __name__ == "__main__":
    unittest.main()
