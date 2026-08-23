"""M220-B3: generic entity facts stay independent of GIS vocabulary."""

from __future__ import annotations

import unittest

from agent.capability_catalog import project_clarification_requirements
from agent.capability_discovery import discover_from_catalog
from agent.request_model import RequestFacts


class M220GenericFactsTests(unittest.TestCase):
    def test_entity_bag_drives_discovery_and_clarification(self):
        definition = {
            "id": "document_lookup",
            "request_hints": {
                "phrases": (),
                "tasks": ("lookup",),
                "required_entities": ("document_id",),
            },
            "request_requirements": {
                "clarification_fields": [
                    {"id": "document", "label": "文档", "kind": "entity", "key": "document_id"}
                ]
            },
        }
        complete = RequestFacts(
            text="查询文档",
            admin_name=None,
            tasks=("lookup",),
            datasets=("documents",),
            constraints={},
            evidence=(),
            entities={"document_id": "doc-7"},
        )
        discovery = discover_from_catalog("查询文档", complete, (definition,))
        self.assertEqual(discovery.as_context_dict()["entities"]["document_id"], "doc-7")
        self.assertEqual(discovery.selected.capability_id, "document_lookup")
        self.assertEqual(
            project_clarification_requirements(
                ["document_lookup"], complete, capability_definitions=(definition,)
            )["missing_fields"],
            [],
        )

        missing = RequestFacts(
            text="查询文档",
            admin_name=None,
            tasks=("lookup",),
            datasets=("documents",),
            constraints={},
            evidence=(),
        )
        self.assertEqual(
            project_clarification_requirements(
                ["document_lookup"], missing, capability_definitions=(definition,)
            )["missing_fields"][0]["id"],
            "document",
        )


if __name__ == "__main__":
    unittest.main()
