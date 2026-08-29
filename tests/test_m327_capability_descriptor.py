"""M327-A contract tests for the shared capability descriptor seam."""

import unittest

from agent.capability_catalog import capability_catalog
from agent.capability_descriptor import (
    CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
    build_capability_descriptor,
    normalize_capability_descriptor,
    project_capability_descriptors,
)
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.indicators.domain import IndicatorsDomainPack


def _definition():
    return {
        "id": "regional_analysis",
        "label": "区域分析",
        "description": "根据登记的数据完成区域分析。",
        "datasets": ["regional_data"],
        "tools": ["regional_query"],
        "result_types": ["regional_metrics_result"],
        "analysis_operations": ["query", "aggregate"],
        "environments": ["local", "production"],
        "geometry": "none",
        "request_requirements": {
            "entities": ["region"],
            "constraints": ["period"],
            "clarification_fields": [
                {"id": "region", "label": "分析区域", "kind": "entity"},
                {"id": "period", "label": "分析期间", "kind": "constraint"},
            ],
        },
        "evidence_requirements": {
            "required": ["dataset_provenance", "execution_receipt"],
        },
        "cost_hint": {"class": "medium", "estimated_step_count": 2},
        "available": True,
        "availability_mode": "native",
        "capability_status": "ready",
        "availability_reason": "native_backend_supported",
        "internal_prompt": "must never appear in a descriptor",
    }


class M327CapabilityDescriptorTests(unittest.TestCase):
    def test_builds_a_bounded_domain_neutral_descriptor(self):
        descriptor = build_capability_descriptor(
            _definition(),
            domain_id="regional",
            catalog_version="1.0",
        )

        self.assertEqual(
            descriptor["schema_version"],
            CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
        )
        self.assertEqual(descriptor["domain_id"], "regional")
        self.assertEqual(descriptor["capability_id"], "regional_analysis")
        self.assertEqual(descriptor["inputs"]["facts"], ["region", "period"])
        self.assertEqual(descriptor["outputs"]["result_types"], ["regional_metrics_result"])
        self.assertEqual(descriptor["execution"]["tools"], ["regional_query"])
        self.assertEqual(
            descriptor["evidence_requirements"]["required"],
            ["dataset_provenance", "execution_receipt"],
        )
        self.assertEqual(descriptor["cost_hint"]["estimated_step_count"], 2)
        self.assertNotIn("internal_prompt", str(descriptor))

    def test_catalog_exposes_detached_descriptors_for_non_gis_domain(self):
        catalog = TEXT_DOMAIN_PACK.capability_catalog(environment="memory")

        self.assertGreater(catalog["capability_descriptor_count"], 0)
        self.assertEqual(
            catalog["capability_descriptor_schema_version"],
            CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
        )
        descriptor = catalog["capability_descriptors"][0]
        self.assertEqual(descriptor["domain_id"], "text")
        self.assertIn("inputs", descriptor)
        self.assertIn("outputs", descriptor)

        descriptor["label"] = "changed"
        fresh = TEXT_DOMAIN_PACK.capability_catalog(environment="memory")
        self.assertNotEqual(fresh["capability_descriptors"][0]["label"], "changed")

    def test_invalid_and_future_descriptors_are_not_projected(self):
        projected = project_capability_descriptors(
            [_definition(), {"label": "缺少身份"}, None],
            domain_id="regional",
        )
        self.assertEqual(len(projected), 1)

        self.assertIsNone(normalize_capability_descriptor({"schema_version": "future"}))
        self.assertIsNone(normalize_capability_descriptor({"schema_version": CAPABILITY_DESCRIPTOR_SCHEMA_VERSION}))

        normalized = normalize_capability_descriptor(projected[0])
        self.assertEqual(normalized, projected[0])

    def test_catalog_adds_descriptor_without_changing_legacy_capability_shape(self):
        catalog = capability_catalog(
            domain_id="regional",
            capability_definitions=(_definition(),),
            dataset_tool_capabilities={"regional_data": ["regional_query"]},
            dataset_groups={"core": ["regional_data"]},
            workflow_templates={},
            analysis_ready_capability_ids=(),
        )

        self.assertEqual(catalog["capabilities"][0]["id"], "regional_analysis")
        self.assertEqual(catalog["capability_descriptor_count"], 1)
        self.assertEqual(
            catalog["capability_descriptors"][0]["capability_id"],
            "regional_analysis",
        )

    def test_indicator_capabilities_bind_to_their_registered_workflows(self):
        catalog = IndicatorsDomainPack().capability_catalog(environment="local")
        bindings = {
            item["id"]: item.get("workflow_ids")
            for item in catalog["capabilities"]
        }
        self.assertEqual(
            bindings,
            {
                "indicator_discovery": ["indicator_discovery"],
                "indicator_latest": ["indicator_latest"],
                "indicator_trend": ["indicator_trend"],
                "indicator_compare": ["indicator_compare"],
            },
        )


if __name__ == "__main__":
    unittest.main()
