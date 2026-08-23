"""M220: workflow validation and composition accept Domain-owned catalogs."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import unittest
from unittest.mock import patch

from agent.workflow_templates import (
    compile_workflow_composition,
    compile_workflow_plan,
    workflow_request_hint,
    workflow_template_context_summary,
)
from agent.domain_contract import workflow_catalog
from agent.llm_planner import LLMPlanner
from agent.service import AgentService
from serve_api import AgentApiHandler
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TextDomainPack


TEXT_TOOL = "summarize_text"
TEXT_RESULT = "text_summary_result"
TEXT_CATALOG = {
    "text_summary": {
        "id": "text_summary",
        "version": "1.0.0",
        "label": "文本摘要",
        "goal_template": "summarize a text source",
        "allowed_tools": [TEXT_TOOL],
        "result_types": [TEXT_RESULT],
        "max_steps": 1,
        "required_constraints": ["source"],
        "constraint_specs": [
            {
                "name": "source",
                "label": "文本来源",
                "type": "string",
                "required": True,
                "min_length": 1,
            }
        ],
        "evidence_options": ["summary", "trace"],
        "default_evidence": ["summary", "trace"],
        "step_blueprint": [
            {
                "id": "summarize",
                "tool": TEXT_TOOL,
                "args": {"source": {"$constraint": "source"}},
                "depends_on": [],
            }
        ],
        "output_template": {"type": TEXT_RESULT, "summary": True},
    }
}


class M220DomainWorkflowSeamTests(unittest.TestCase):
    def _known(self):
        return {
            "known_tools": [TEXT_TOOL],
            "known_result_types": [TEXT_RESULT],
        }

    def test_custom_catalog_context_has_no_gis_defaults(self):
        summary = workflow_template_context_summary(
            catalog=TEXT_CATALOG,
            compact=True,
            **self._known(),
        )

        self.assertEqual(summary["template_count"], 1)
        self.assertEqual(summary["templates"][0]["id"], "text_summary")
        self.assertNotIn("get_raster_metadata", str(summary))

    def test_domain_catalog_seam_does_not_fallback_to_gis(self):
        self.assertIn("spatial_analysis", workflow_catalog(GIS_DOMAIN_PACK))
        self.assertEqual(workflow_catalog(TextDomainPack()), {})

    def test_generic_module_contains_no_embedded_gis_catalog_literal(self):
        source = (Path(__file__).parents[1] / "agent" / "workflow_templates.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("WORKFLOW_TEMPLATE_CATALOG = {", source)
        self.assertIn("domains.gis.workflow_templates", source)

    def test_custom_catalog_compiles_a_valid_plan(self):
        plan = compile_workflow_plan(
            "text_summary",
            {"source": "公开文本"},
            catalog=TEXT_CATALOG,
            **self._known(),
        )

        self.assertEqual(plan["steps"][0]["tool"], TEXT_TOOL)
        self.assertEqual(plan["output"]["type"], TEXT_RESULT)
        self.assertEqual(plan["steps"][0]["args"]["source"], "公开文本")

    def test_custom_catalog_composes_independent_components(self):
        components = [
            {
                "component_id": "first",
                "template_id": "text_summary",
                "constraints": {"source": "第一段"},
            },
            {
                "component_id": "second",
                "template_id": "text_summary",
                "constraints": {"source": "第二段"},
                "depends_on_components": ["first"],
            },
        ]

        plan = compile_workflow_composition(
            components,
            catalog=TEXT_CATALOG,
            output_type="text_summary_result",
            **self._known(),
        )

        self.assertEqual(len(plan["steps"]), 2)
        self.assertTrue(plan["steps"][0]["id"].startswith("first--"))
        second = next(item for item in plan["steps"] if item["id"].startswith("second--"))
        self.assertTrue(any(item.startswith("first--") for item in second["depends_on"]))

    def test_generic_hint_forwards_safe_custom_constraints_only(self):
        hint = workflow_request_hint(
            "请处理这段内容",
            {
                "template_id": "text_summary",
                "constraints": {
                    "source": "公开文本",
                    "api_key": "must-not-forward",
                },
            },
        )

        self.assertIn("source=公开文本", hint)
        self.assertNotIn("must-not-forward", hint)
        self.assertNotIn("get_raster_metadata", hint)

    def test_llm_planner_uses_domain_hint_adapter_without_gis_import(self):
        class Client:
            def __init__(self):
                self.messages = []

            def complete_json(self, messages, schema):
                del schema
                self.messages = messages
                return {
                    "goal": "summarize text",
                    "steps": [
                        {"id": "summarize", "tool": TEXT_TOOL, "args": {"source": "公开文本"}}
                    ],
                    "output": {"type": TEXT_RESULT},
                }

        client = Client()
        LLMPlanner(
            client,
            [TEXT_TOOL],
            request_hint=lambda request, workflow: workflow_request_hint(request, workflow),
        ).plan(
            "请处理这段内容",
            workflow={"template_id": "text_summary", "constraints": {"source": "公开文本"}},
        )

        self.assertIn("source=公开文本", client.messages[1]["content"])
        self.assertNotIn("get_raster_metadata", client.messages[1]["content"])

    def test_dev_http_workflow_contract_uses_selected_domain_catalog(self):
        class TemplateTextDomain(TextDomainPack):
            def workflow_template_catalog(self):
                return TEXT_CATALOG

        selected_service = AgentService(domain_pack=TemplateTextDomain())

        class Handler(AgentApiHandler):
            service = selected_service

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/workflows?planner=rule&backend=memory")
            get_response = connection.getresponse()
            catalog_payload = json.loads(get_response.read().decode("utf-8"))
            connection.request(
                "POST",
                "/workflows/text_summary/validate",
                body=json.dumps(
                    {"constraints": {"source": "公开文本"}},
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            post_response = connection.getresponse()
            validation_payload = json.loads(post_response.read().decode("utf-8"))
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            selected_service.close()

        self.assertEqual(get_response.status, 200)
        self.assertEqual(catalog_payload["domain_id"], "text")
        self.assertEqual(set(catalog_payload["templates"]), {"text_summary"})
        self.assertEqual(post_response.status, 200)
        self.assertEqual(validation_payload["constraints"]["source"], "公开文本")

    def test_production_http_workflow_contract_uses_selected_domain_catalog(self):
        import production_api

        class TemplateTextDomain(TextDomainPack):
            def workflow_template_catalog(self):
                return TEXT_CATALOG

        selected_service = AgentService(domain_pack=TemplateTextDomain())
        try:
            with patch.object(production_api, "service", selected_service):
                catalog_payload = production_api.workflows()
                validation_payload = production_api.validate_workflow(
                    "text_summary",
                    {"constraints": {"source": "公开文本"}},
                )
        finally:
            selected_service.close()

        self.assertEqual(catalog_payload["domain_id"], "text")
        self.assertEqual(set(catalog_payload["templates"]), {"text_summary"})
        self.assertEqual(validation_payload["constraints"]["source"], "公开文本")


if __name__ == "__main__":
    unittest.main()
