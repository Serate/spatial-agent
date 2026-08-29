"""M140 verifies catalog-owned clarification requirements."""

import unittest
from pathlib import Path
from unittest.mock import patch

from agent.capability_catalog import (
    capability_catalog,
    capability_context_summary,
    project_clarification_requirements,
)
from agent.request_model import RequestFacts
from domains.gis.intent import clarification_details
from domains.gis.evidence import GIS_EVIDENCE_PROVIDER
from domains.text.domain import TEXT_DOMAIN_PACK


class M140CapabilityRequirementsTests(unittest.TestCase):
    def test_projection_is_generic_for_custom_capability_ids(self):
        definitions = (
            {
                "id": "custom_analysis",
                "label": "自定义分析",
                "datasets": [],
                "tools": [],
                "result_types": ["custom_result"],
                "environments": ["memory"],
                "geometry": "none",
                "request_requirements": {
                    "entities": ["area"],
                    "constraints": ["limit"],
                    "clarification_fields": [
                        {
                            "id": "area",
                            "label": "分析区域",
                            "kind": "entity",
                            "key": "region",
                        },
                        {
                            "id": "limit",
                            "label": "分析阈值",
                            "kind": "constraint",
                            "keys": ["limit"],
                        },
                    ],
                },
            },
        )
        facts = RequestFacts(
            text="",
            admin_name=None,
            tasks=(),
            datasets=(),
            constraints={},
            evidence=(),
        )

        catalog = capability_catalog(
            domain_id="custom",
            capability_definitions=definitions,
            dataset_tool_capabilities={},
            dataset_groups={},
            workflow_templates={},
            analysis_ready_capability_ids=(),
        )
        item = catalog["capabilities"][0]
        self.assertEqual(
            item["request_requirements"]["clarification_fields"][0]["id"],
            "area",
        )
        projection = project_clarification_requirements(
            ["custom_analysis"],
            facts,
            capability_definitions=definitions,
        )
        self.assertEqual(projection["missing"], ["分析区域", "分析阈值"])

        complete = project_clarification_requirements(
            ["custom_analysis"],
            {
                "region": "测试区域",
                "datasets": [],
                "constraints": {"limit": 5},
            },
            capability_definitions=definitions,
        )
        self.assertEqual(complete["missing"], [])

    def test_gis_intent_projects_from_declarations(self):
        source = Path("domains/gis/intent.py").read_text(encoding="utf-8")
        self.assertNotIn("capability_id in", source)
        self.assertIn("project_clarification_requirements", source)

        incomplete = clarification_details("建设适宜性")
        self.assertIn("区域或行政区", incomplete["missing"])
        self.assertIn("筛选阈值", incomplete["missing"])

        complete = clarification_details(
            "分析洪山区建设适宜性，使用DEM，坡度不超过20度"
        )
        self.assertEqual(complete["missing"], [])
        self.assertEqual(complete["missing_fields"], [])

    def test_dataset_and_constraint_requirements_are_distinct(self):
        missing_dataset = clarification_details("分析洪山区坡度")
        self.assertNotIn("区域或行政区", missing_dataset["missing"])
        self.assertIn("数据集", missing_dataset["missing"])

        missing_constraints = clarification_details(
            "分析洪山区建设适宜性，坡度不超过20度，距离道路不超过1000米"
        )
        self.assertIn("筛选阈值", missing_constraints["missing"])

    def test_context_and_text_domain_remain_bounded(self):
        catalog = capability_catalog()
        summary = capability_context_summary(
            catalog=catalog,
            selected_capability_ids=["buildability_screening"],
        )
        requirements = summary["capabilities"][0]["request_requirements"]
        self.assertEqual(requirements["schema_version"], "spatial-agent.capability-requirements.v1")
        self.assertIn("clarification_fields", requirements)

        text_catalog = TEXT_DOMAIN_PACK.capability_catalog()
        text_requirements = text_catalog["capabilities"][0]["request_requirements"]
        self.assertEqual(text_requirements["clarification_fields"], [])
        self.assertNotIn("洪山区", str(text_requirements))
        self.assertNotIn("DEM", str(text_requirements))

    def test_gis_evidence_adapter_normalizes_legacy_capability_key(self):
        legacy = {
            "capabilities": [{"id": "conversation", "runtime_evidence": {}}],
            "health_status": "ready",
        }
        with patch(
            "domains.gis.adapters.runtime_capabilities.runtime_capability_snapshot",
            return_value=legacy,
        ):
            result = GIS_EVIDENCE_PROVIDER.runtime_snapshot(max_files=1)

        self.assertEqual(result["capabilities_runtime"], legacy["capabilities"])
        self.assertEqual(result["capabilities"], legacy["capabilities"])


if __name__ == "__main__":
    unittest.main()
