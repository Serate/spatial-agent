"""M167: candidate details stay bounded and drive a domain-neutral Console choice."""

from pathlib import Path
import unittest

from agent.runtime_factory import build_runtime
from agent.selection_interaction import build_selection_interaction
from agent.workflow_selection import (
    build_workflow_selection_evidence,
    normalize_workflow_selection_evidence,
)
from domains.text.domain import TEXT_DOMAIN_PACK


class M167CandidateSelectionTests(unittest.TestCase):
    def test_catalog_projects_candidate_details_without_domain_branches(self):
        selection = build_workflow_selection_evidence(
            discovery={"candidate_ids": ["summary", "inspect"]},
            domain_id="example",
            capability_catalog={
                "capabilities": [
                    {
                        "id": "summary",
                        "label": "内容摘要",
                        "description": "把输入内容压缩为可读摘要。",
                        "available": True,
                        "result_types": ["summary_result"],
                        "request_requirements": {
                            "clarification_fields": [
                                {"id": "source", "label": "输入来源", "kind": "entity"}
                            ]
                        },
                    },
                    {"id": "inspect", "label": "内容检查", "available": False},
                ],
                "workflow_templates": {
                    "summary": {
                        "id": "summary",
                        "version": "2.0.0",
                        "result_types": ["summary_result"],
                        "max_steps": 3,
                    }
                },
            },
        )

        details = selection["candidate_details"]
        self.assertEqual([item["id"] for item in details], ["summary", "inspect"])
        self.assertEqual(details[0]["workflow"]["template_version"], "2.0.0")
        self.assertEqual(details[0]["input_facts"][0]["id"], "source")
        self.assertFalse(details[1]["available"])
        self.assertEqual(details[0]["actions"], ["select_capability", "select_workflow"])

    def test_selection_and_interaction_preserve_candidate_details(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)
        result = runtime.run("概括这段文本")
        selection = result.plan_evidence["workflow_selection"]
        self.assertEqual(selection["candidate_details"][0]["id"], "text_summary")
        self.assertTrue(selection["candidate_details"][0]["description"])

        interaction = build_selection_interaction(
            selection=selection,
            status="NEEDS_CLARIFICATION",
        )
        self.assertEqual(
            interaction["selection"]["candidate_details"][0]["id"], "text_summary"
        )
        restored = normalize_workflow_selection_evidence(selection)
        self.assertEqual(restored["candidate_details"], selection["candidate_details"])

    def test_console_submits_capability_id_and_renders_cards(self):
        root = Path(__file__).parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        module = (root / "web" / "console_interaction.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("selection-candidate-grid", html)
        self.assertIn("data-canonical-action-host", html)
        self.assertIn("renderCanonicalInteraction", html)
        self.assertIn("function candidates", module)
        self.assertNotIn("admin_name", module)
        browser_smoke = root / "scripts" / "console_candidate_selection_browser_smoke.js"
        self.assertTrue(browser_smoke.exists())
        smoke_source = browser_smoke.read_text(encoding="utf-8")
        self.assertIn("capability_id", smoke_source)
        self.assertIn("editorOpen", smoke_source)


if __name__ == "__main__":
    unittest.main()
