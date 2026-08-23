"""M165: cross-entry contracts include bounded selection interaction."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from agent.service_async import build_async_result_evidence
from agent.selection_interaction import build_selection_interaction
from agent.workflow_selection import build_workflow_selection_evidence
from evaluation.contract_harness import compare_results, normalize_result


def _selection():
    return build_workflow_selection_evidence(
        discovery={
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
        },
        domain_id="text",
        domain_selection={
            "candidate_ids": ["text_summary"],
            "selected_capability_id": "text_summary",
        },
    )


def _interaction(subject_id="run-a", decision_id="decision-a"):
    return build_selection_interaction(
        selection=_selection(),
        status="WAITING_FOR_DECISION",
        decision={
            "decision_id": decision_id,
            "status": "PENDING",
            "version": 3,
            "options": ["approve", "reject"],
        },
        subject_id=subject_id,
    )


def _payload():
    return {
        "run_id": "run-a",
        "status": "WAITING_FOR_DECISION",
        "answer": "等待确认",
        "steps": [],
        "trace_summary": [],
        "result": {
            "type": "text_summary_result",
            "title": "文本摘要",
            "selection_interaction": _interaction(),
            "planning": {
                "workflow_selection": _selection(),
            },
            "lineage": {"artifact": {"available": True}},
            "views": {
                "schema_version": "spatial-agent.views.v1",
                "panels": {},
            },
        },
    }


class M165CrossEntryContractTests(unittest.TestCase):
    def test_console_assets_are_allowlisted_in_both_http_entries(self):
        root = Path(__file__).parents[1]
        production = (root / "production_api.py").read_text(encoding="utf-8")
        development = (root / "serve_api.py").read_text(encoding="utf-8")
        for source in (production, development):
            for asset in (
                "console_selection_interaction.js",
                "console_evidence_registry.js",
                "console_renderer_registry.js",
                "console_action_host.js",
                "console_gis_plugin.js",
            ):
                self.assertIn(asset, source)
            self.assertIn("application/javascript", source)

    def test_selection_interaction_is_transport_neutral(self):
        first = _payload()
        second = copy.deepcopy(first)
        second["run_id"] = "run-b"
        second["result"]["selection_interaction"]["subject_id"] = "run-b"
        second["result"]["selection_interaction"]["decision"]["decision_id"] = "decision-b"
        self.assertEqual(compare_results([first, second]), [])

    def test_selection_interaction_drift_is_reported(self):
        changed = _payload()
        changed["result"]["selection_interaction"] = build_selection_interaction(
            selection=_selection(),
            status="COMPLETED",
        )
        differences = compare_results([_payload(), changed])
        self.assertTrue(
            any("$.selection_interaction.state" in item for item in differences),
            differences,
        )

    def test_async_projection_carries_same_bounded_interaction(self):
        payload = _payload()
        contract = payload["result"]
        evidence = build_async_result_evidence(
            contract,
            status="WAITING_FOR_DECISION",
        )
        self.assertEqual(evidence["state"], "pending")
        payload["async_observability"] = {"result_evidence": evidence}
        normalized = normalize_result(payload).as_dict()
        interaction = normalized["async_result_evidence"]["selection_interaction"]
        self.assertEqual(interaction["state"], "confirmation_required")
        self.assertNotIn("subject_id", interaction)
        self.assertNotIn("decision_id", interaction.get("decision") or {})


if __name__ == "__main__":
    unittest.main()
