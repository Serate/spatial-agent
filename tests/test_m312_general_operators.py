"""M312-A compact contracts for operation/workflow/result closure."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.operation_binding import inspect_operation_binding
from agent.domain_runtime_host import DomainRuntimeHost
from agent.application.composite_planning import CompositeCapabilityProjector
from agent.runtime_core.plan_completeness import assess_catalog_consistency
from domains.economic.domain import EconomicDomainPack
from domains.economic.planner import EconomicRulePlanner
from domains.economic.provider import EconomicToolProvider
from domains.gis.domain import GisDomainPack


def _domain_projection(pack):
    catalog = pack.capability_catalog(environment="memory")
    workflows = pack.workflow_template_catalog()
    result_context = pack.result_registry().as_context()
    result_types = [
        item["type"]
        for item in result_context["result_types"]
        if isinstance(item, dict) and item.get("type")
    ]
    result_profiles = {
        item["type"]: {
            "schema_version": "spatial-agent.data-profile.v1",
            "primary": (item.get("data_kinds") or ["unknown"])[0],
            "kinds": list(item.get("data_kinds") or ["unknown"]),
        }
        for item in result_context["result_types"]
        if isinstance(item, dict) and item.get("type")
    }
    tool_names = sorted(
        {
            tool
            for template in workflows.values()
            for tool in template.get("allowed_tools", [])
        }
    )
    return {
        "domain_id": pack.domain_id,
        "capabilities": catalog["capabilities"],
        "workflows": list(workflows.values()),
        "execution_contract": {
            "status": "valid",
            "tool_names": tool_names,
            "tool_definitions": {name: {} for name in tool_names},
            "result_type_ids": result_types,
            "result_profiles": result_profiles,
        },
    }


class M312GeneralOperatorsTests(unittest.TestCase):
    def test_real_domain_catalogs_have_unambiguous_operation_closure(self):
        receipt = assess_catalog_consistency(
            {
                "domains": [
                    _domain_projection(GisDomainPack()),
                    _domain_projection(EconomicDomainPack()),
                ]
            }
        )
        bindings = {
            (item["domain_id"], item["capability_id"]): item
            for item in receipt["bindings"]
        }
        vector = bindings[("gis", "vector_operation")]
        economic = bindings[("economic", "economic_indicator_trend")]
        self.assertEqual(vector["workflow_ids"], ["vector_operation"])
        self.assertEqual(vector["operation_binding"]["status"], "ready")
        self.assertEqual(economic["workflow_ids"], ["economic_trend"])
        self.assertEqual(economic["operation_binding"]["status"], "ready")
        self.assertFalse(
            any(
                item["operation_binding"].get("reason_code")
                == "workflow_binding_ambiguous"
                for item in receipt["bindings"]
            )
        )

    def test_compatible_tool_and_result_subsets_do_not_guess_a_workflow(self):
        receipt = assess_catalog_consistency(
            {
                "domains": [
                    {
                        "domain_id": "demo",
                        "capabilities": [
                            {
                                "id": "distance_capability",
                                "tools": ["spatial_operation"],
                                "result_types": ["spatial_result"],
                                "analysis_operations": ["spatial_operation"],
                            }
                        ],
                        "workflows": [
                            {
                                "id": "vector_operation",
                                "allowed_tools": ["spatial_operation"],
                                "result_types": ["spatial_result"],
                            },
                            {
                                "id": "vector_measurement",
                                "allowed_tools": ["spatial_operation"],
                                "result_types": ["spatial_result"],
                            },
                        ],
                        "execution_contract": {
                            "status": "valid",
                            "tool_names": ["spatial_operation"],
                            "result_type_ids": ["spatial_result"],
                            "result_profiles": {
                                "spatial_result": {"kinds": ["vector"]}
                            },
                        },
                    }
                ]
            }
        )
        binding = receipt["bindings"][0]
        self.assertEqual(binding["plan_mode"], "unbound")
        self.assertEqual(binding["operation_binding"]["reason_code"], "workflow_unbound")

    def test_spatial_operation_rejects_incompatible_result_profile(self):
        binding = inspect_operation_binding(
            {
                "tools": ["spatial_operation"],
                "analysis_operations": ["spatial_operation"],
                "result_types": ["metrics_result"],
            },
            workflow_ids=["vector_operation"],
            result_profiles={"metrics_result": {"kinds": ["metrics"]}},
        )
        self.assertEqual(binding["status"], "invalid")
        self.assertEqual(binding["reason_code"], "operation_result_profile_mismatch")

    def test_declared_operation_without_profiles_is_not_execution_ready(self):
        binding = inspect_operation_binding(
            {
                "tools": ["economic_indicator_query"],
                "analysis_operations": ["trend"],
                "result_types": ["timeseries_result"],
            },
            workflow_ids=["economic_trend"],
            result_profiles=None,
        )
        self.assertEqual(binding["status"], "unknown")
        self.assertEqual(binding["reason_code"], "result_profiles_unknown")

    def test_multiple_workflow_bindings_fail_closed(self):
        binding = inspect_operation_binding(
            {
                "tools": ["spatial_operation"],
                "analysis_operations": ["spatial_operation"],
                "result_types": ["vector_result"],
            },
            workflow_ids=["vector_operation", "vector_measurement"],
            result_profiles={"vector_result": {"kinds": ["vector"]}},
        )
        self.assertEqual(binding["status"], "invalid")
        self.assertEqual(binding["reason_code"], "workflow_binding_ambiguous")

    def test_gis_operations_share_result_profile_and_preserve_output_crs(self):
        import geopandas as gpd
        from shapely.geometry import Polygon
        from domains.gis.adapters.spatial_backend import GeoPackageBackend

        backend = GeoPackageBackend.__new__(GeoPackageBackend)
        backend._entries = {}
        backend._cache = {}
        backend._result_cache = {
            "input": gpd.GeoDataFrame(
                {"name": ["input"]},
                geometry=[Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])],
                crs="EPSG:4326",
            ),
            "mask": gpd.GeoDataFrame(
                {"name": ["mask"]},
                geometry=[Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])],
                crs="EPSG:3857",
            ),
        }
        backend._result_number = 0
        for operation, distance in (
            ("clip", None),
            ("intersect", None),
            ("buffer", 100.0),
            ("distance", 100.0),
        ):
            with self.subTest(operation=operation):
                result = backend.spatial_operation(
                    operation,
                    "input",
                    "mask",
                    max_features=10,
                    distance_m=distance,
                )
                self.assertEqual(result["data_profile"]["primary"], "vector")
                self.assertEqual(result["crs"], "EPSG:4326")
                self.assertTrue(result["summary"]["reprojected_mask"])
                self.assertIn("returned_features", result["summary"])

    def test_gis_operation_empty_intersection_is_a_valid_empty_result(self):
        import geopandas as gpd
        from shapely.geometry import Polygon
        from domains.gis.adapters.spatial_backend import GeoPackageBackend

        backend = GeoPackageBackend.__new__(GeoPackageBackend)
        backend._entries = {}
        backend._cache = {}
        backend._result_cache = {
            "input": gpd.GeoDataFrame(
                {"name": ["input"]},
                geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
                crs="EPSG:4326",
            ),
            "mask": gpd.GeoDataFrame(
                {"name": ["mask"]},
                geometry=[Polygon([(3, 3), (4, 3), (4, 4), (3, 4)])],
                crs="EPSG:4326",
            ),
        }
        backend._result_number = 0
        result = backend.spatial_operation(
            "intersect", "input", "mask", max_features=10
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["summary"]["returned_features"], 0)
        self.assertEqual(result["data_profile"]["primary"], "vector")

    def test_economic_real_dataset_keeps_query_and_evidence_profiles_distinct(self):
        provider = EconomicToolProvider()
        self.assertEqual(provider.health()["status"], "ready")
        query = provider.invoke(
            "economic_indicator_query",
            {
                "dataset": "wuhan_hongshan_economic_indicators",
                "operation": "trend",
                "indicator": "gdp_total",
                "regions": ["洪山区"],
                "geography_level": "district",
                "period_type": "annual",
                "period_start": "2022",
                "period_end": "2025",
            },
        )
        evidence = provider.invoke(
            "economic_source_evidence",
            {
                "dataset": "wuhan_hongshan_economic_indicators",
                "indicator": "gdp_total",
                "regions": ["洪山区"],
                "geography_level": "district",
                "period_type": "annual",
                "period_start": "2022",
                "period_end": "2025",
            },
        )
        self.assertEqual(query["data_profile"]["primary"], "timeseries")
        self.assertEqual(evidence["data_profile"]["primary"], "document_evidence")
        self.assertEqual(evidence["result_type"], "economic_evidence_result")
        self.assertEqual(len(query["rows"]), len(evidence["sources"]))

    def test_economic_evidence_failure_preserves_document_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "economic.json"
            path.write_text(json.dumps({"records": []}), encoding="utf-8")
            evidence = EconomicToolProvider(str(path)).invoke(
                "economic_source_evidence",
                {
                    "dataset": "wuhan_hongshan_economic_indicators",
                    "indicator": "gdp_total",
                    "regions": ["洪山区"],
                },
            )
        self.assertEqual(evidence["status"], "unavailable")
        self.assertEqual(evidence["data_profile"]["primary"], "document_evidence")
        self.assertEqual(evidence["result_type"], "economic_evidence_result")
        self.assertEqual(evidence["sources"], [])

    def test_economic_rule_plan_binds_optional_time_and_geography_constraints(self):
        plan = EconomicRulePlanner().plan(
            "指标为gdp_total 洪山区趋势 区级 2022年至2025年"
        )
        self.assertEqual(plan.output["type"], "economic_timeseries_result")
        self.assertEqual(plan.steps[0].args["geography_level"], "district")
        self.assertEqual(plan.steps[0].args["period_start"], "2022")
        self.assertEqual(plan.steps[0].args["period_end"], "2025")
        self.assertEqual(plan.steps[1].args["geography_level"], "district")

    def test_composite_projector_preserves_domain_workflow_identity(self):
        host = DomainRuntimeHost()
        host.start()
        try:
            context = CompositeCapabilityProjector(host).project(
                planner="rule",
                backend="local",
                domain_ids=["gis", "economic", "indicators"],
            )
        finally:
            host.close()
        entries = {
            (item["domain_id"], item["capability_id"]): item
            for item in context["capability_index"]
        }
        self.assertEqual(entries[("gis", "spatial_overview")]["workflow_ids"], ["spatial_overview"])
        self.assertEqual(entries[("economic", "economic_indicator_discovery")]["workflow_ids"], ["economic_discovery"])
        self.assertTrue(entries[("gis", "spatial_overview")]["execution_ready"])
        self.assertTrue(entries[("economic", "economic_indicator_discovery")]["execution_ready"])


if __name__ == "__main__":
    unittest.main()
