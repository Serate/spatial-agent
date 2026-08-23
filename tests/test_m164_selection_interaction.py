"""M164: workflow selection exposes one bounded next-action projection."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from agent.service import AgentService
from agent.service_async import build_async_result_evidence
from agent.selection_interaction import (
    SELECTION_INTERACTION_SCHEMA_VERSION,
    build_selection_interaction,
    normalize_selection_interaction,
)
from agent.workflow_selection import build_workflow_selection_evidence
from result_contract import build_result_contract
from domains.text.runtime import build_text_runtime


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _selection(**overrides):
    value = {
        "discovery": {
            "candidate_ids": ["capability_a", "capability_b"],
            "candidate_count": 2,
        },
        "domain_id": "example",
    }
    value.update(overrides)
    return build_workflow_selection_evidence(**value)


class M164SelectionInteractionTests(unittest.TestCase):
    def test_ambiguous_selection_exposes_choice_actions(self):
        interaction = build_selection_interaction(
            selection=_selection(),
            status="NEEDS_CLARIFICATION",
            subject_id="run-1",
        )
        self.assertEqual(interaction["schema_version"], SELECTION_INTERACTION_SCHEMA_VERSION)
        self.assertEqual(interaction["state"], "candidate_selection")
        self.assertEqual(
            interaction["allowed_actions"],
            ["select_capability", "select_workflow", "cancel"],
        )
        self.assertEqual(interaction["subject_id"], "run-1")

    def test_missing_facts_precede_confirmation(self):
        interaction = build_selection_interaction(
            selection=_selection(
                domain_selection={
                    "candidate_ids": ["capability_a"],
                    "missing_fields": [
                        {"id": "region", "label": "分析区域", "kind": "fact"}
                    ],
                }
            ),
            status="WAITING_FOR_DECISION",
            decision={
                "decision_id": "decision-1",
                "status": "PENDING",
                "version": 2,
                "options": ["approve", "reject"],
            },
        )
        self.assertEqual(interaction["state"], "facts_required")
        self.assertIn("provide_facts", interaction["allowed_actions"])
        self.assertNotIn("confirm", interaction["allowed_actions"])
        self.assertEqual(interaction["missing_fields"][0]["id"], "region")

    def test_result_and_async_projection_share_interaction(self):
        selection = _selection(
            domain_selection={
                "candidate_ids": ["capability_a"],
                "selected_capability_id": "capability_a",
            }
        )
        payload = {
            "run_id": "run-2",
            "status": "WAITING_FOR_DECISION",
            "result_type": "text_summary_result",
            "request": "总结文本",
            "plan": {"goal": "总结", "steps": [], "output": {"type": "text_summary_result"}},
            "plan_evidence": {"workflow_selection": selection},
            "decision_evidence": {
                "decision_id": "decision-2",
                "status": "PENDING",
                "version": 1,
                "options": ["approve", "reject"],
            },
            "answer": "等待确认",
            "steps": [],
        }
        contract = build_result_contract(payload)
        async_evidence = build_async_result_evidence(
            contract, status="WAITING_FOR_DECISION"
        )
        self.assertEqual(
            contract["selection_interaction"]["schema_version"],
            SELECTION_INTERACTION_SCHEMA_VERSION,
        )
        self.assertEqual(
            async_evidence["selection_interaction"],
            contract["selection_interaction"],
        )

    def test_unknown_interaction_schema_is_unavailable(self):
        value = normalize_selection_interaction(
            {"schema_version": "future.v9", "subject_id": "run-3"}
        )
        self.assertEqual(value["schema_version"], SELECTION_INTERACTION_SCHEMA_VERSION)
        self.assertEqual(value["state"], "unavailable")
        self.assertEqual(value["allowed_actions"], [])

    def test_service_interaction_read_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="m164-interaction-") as directory:
            service = AgentService(
                state_db_path=str(Path(directory) / "state.db"),
                runtime_factory=_text_runtime_factory,
            )
            try:
                result = service.run(request="概括一段文本", planner="rule", backend="memory")
                projection = service.get_run_interaction(result["run_id"])
                self.assertEqual(
                    projection["schema_version"],
                    "spatial-agent.selection-interaction-reference.v1",
                )
                self.assertEqual(projection["interaction"]["state"], "completed")
                self.assertNotIn("概括一段文本", str(projection))
            finally:
                service.close()

    def test_confirmation_action_dispatches_through_decision_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="m164-action-") as directory:
            service = AgentService(
                state_db_path=str(Path(directory) / "state.db"),
                runtime_factory=_text_runtime_factory,
            )
            try:
                waiting = service.run(
                    request="概括一段文本",
                    planner="rule",
                    backend="memory",
                    require_confirmation=True,
                )
                self.assertEqual(waiting["status"], "WAITING_FOR_DECISION")
                interaction = service.get_run_interaction(waiting["run_id"])
                self.assertIn("confirm", interaction["interaction"]["allowed_actions"])
                completed = service.apply_run_interaction(
                    waiting["run_id"], "confirm", {}, planner="rule", backend="memory"
                )
                self.assertEqual(completed["status"], "COMPLETED")
            finally:
                service.close()

    def test_console_consumes_canonical_interaction_without_domain_branch(self):
        root = Path(__file__).parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        module = (root / "web" / "console_interaction.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('console_interaction.js', html)
        self.assertNotIn('console_selection_interaction.js', html)
        self.assertIn('renderCanonicalInteraction', html)
        self.assertIn('spatial-agent.interaction.v1', module)
        self.assertNotIn('admin_name', module)


if __name__ == "__main__":
    unittest.main()
