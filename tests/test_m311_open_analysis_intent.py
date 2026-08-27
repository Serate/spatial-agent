"""M311-A: bounded, domain-neutral analysis intent contract."""

from __future__ import annotations

import unittest

from agent.analysis_intent import (
    ANALYSIS_INTENT_SCHEMA_VERSION,
    AnalysisIntentError,
    normalize_analysis_intent,
)
from agent.errors import PlanningError
from agent.llm_planner import LLMPlanner
from agent.runtime_core.planner_envelope import (
    PlannerEnvelopeError,
    build_planner_envelope,
    normalize_planner_envelope,
)
from agent.composite_planner import CompositePlannerError, normalize_composite_plan
from agent.composite_view import build_composite_view_projection
from agent.application.composite_runs import _safe_planning_evidence
from domains.economic.domain import EconomicDomainPack
from domains.gis.domain import GisDomainPack


class M311AnalysisIntentTests(unittest.TestCase):
    def test_normalizes_operations_data_kinds_and_fact_references(self):
        intent = normalize_analysis_intent(
            {
                "operations": [
                    {"id": "load", "operation": "query", "output_kinds": ["metrics"], "fact_refs": ["indicator"]},
                    {"id": "trend", "kind": "time_series", "depends_on": ["load"], "output_kinds": ["timeseries", "metrics"]},
                    "evidence",
                ],
                "data_kinds": ["metrics", "timeseries", "document_evidence"],
                "fact_refs": ["indicator", "regions"],
                "source": "planner",
            }
        )
        self.assertEqual(intent["schema_version"], ANALYSIS_INTENT_SCHEMA_VERSION)
        self.assertEqual([item["kind"] for item in intent["operations"]], ["query", "trend", "evidence"])
        self.assertEqual(intent["operations"][1]["depends_on"], ["load"])
        self.assertEqual(intent["operations"][0]["output_kinds"], ["metrics"])
        self.assertEqual(intent["data_kinds"], ["metrics", "timeseries", "document_evidence"])

    def test_rejects_unknown_operation_and_unknown_fields(self):
        with self.assertRaisesRegex(AnalysisIntentError, "unsupported") as operation:
            normalize_analysis_intent({"operations": ["invented_operation"]})
        self.assertEqual(operation.exception.code, "analysis_intent_operation_unsupported")
        with self.assertRaisesRegex(AnalysisIntentError, "unsupported fields") as field:
            normalize_analysis_intent({"operations": ["query"], "private_prompt": "do not carry"})
        self.assertEqual(field.exception.code, "analysis_intent_field_invalid")

    def test_rejects_duplicate_ids_unknown_dependencies_and_cycles(self):
        with self.assertRaisesRegex(AnalysisIntentError, "unique") as duplicate:
            normalize_analysis_intent({"operations": [{"id": "x", "kind": "query"}, {"id": "x", "kind": "evidence"}]})
        self.assertEqual(duplicate.exception.code, "analysis_intent_duplicate_operation")
        with self.assertRaisesRegex(AnalysisIntentError, "unknown") as missing:
            normalize_analysis_intent({"operations": [{"id": "x", "kind": "query", "depends_on": ["missing"]}]})
        self.assertEqual(missing.exception.code, "analysis_intent_dependency_unknown")
        with self.assertRaisesRegex(AnalysisIntentError, "cycle") as cycle:
            normalize_analysis_intent({"operations": [{"id": "x", "kind": "query", "depends_on": ["y"]}, {"id": "y", "kind": "evidence", "depends_on": ["x"]}]})
        self.assertEqual(cycle.exception.code, "analysis_intent_dependency_cycle")

    def test_rejects_invalid_schema_missing_operations_and_bad_kinds(self):
        cases = [
            ({}, "analysis_intent_operations_required"),
            ({"schema_version": "other", "operations": ["query"]}, "analysis_intent_schema_invalid"),
            ({"operations": ["query"], "data_kinds": ["not-a-kind"]}, "analysis_intent_data_kind_invalid"),
        ]
        for payload, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(AnalysisIntentError) as raised:
                    normalize_analysis_intent(payload)
                self.assertEqual(raised.exception.code, code)

    def test_applies_operation_and_fact_limits(self):
        with self.assertRaises(AnalysisIntentError) as too_many_operations:
            normalize_analysis_intent({"operations": ["query"] * 3}, max_operations=2)
        self.assertEqual(too_many_operations.exception.code, "analysis_intent_operations_limit")
        with self.assertRaises(AnalysisIntentError) as bad_refs:
            normalize_analysis_intent({"operations": [{"kind": "query", "fact_refs": "private"}]})
        self.assertEqual(bad_refs.exception.code, "analysis_intent_reference_invalid")

    def test_planner_envelope_carries_only_normalized_intent(self):
        envelope = build_planner_envelope(
            {
                "schema_version": "spatial-agent.composite-request-context.v2",
                "analysis_intent": {
                    "operations": [{"kind": "query", "output_kinds": ["metrics"]}],
                    "data_kinds": ["metrics"],
                    "fact_refs": ["indicator"],
                    "source": "domain",
                },
                "capability_index": [],
                "domain_contexts": [],
            }
        )
        self.assertEqual(envelope["analysis_intent"]["schema_version"], ANALYSIS_INTENT_SCHEMA_VERSION)
        self.assertEqual(envelope["analysis_intent"]["operations"][0]["kind"], "query")
        normalized = normalize_planner_envelope(envelope)
        self.assertEqual(normalized["analysis_intent"]["fact_refs"], ["indicator"])

    def test_planner_envelope_rejects_invalid_intent_instead_of_dropping_it(self):
        with self.assertRaises(PlannerEnvelopeError) as raised:
            build_planner_envelope(
                {
                    "schema_version": "spatial-agent.composite-request-context.v2",
                    "analysis_intent": {"operations": ["unregistered"]},
                    "capability_index": [],
                    "domain_contexts": [],
                }
            )
        self.assertEqual(raised.exception.code, "analysis_intent_invalid")

    def test_planner_envelope_keeps_domain_intents_separate(self):
        envelope = build_planner_envelope(
            {
                "schema_version": "spatial-agent.composite-request-context.v2",
                "capability_index": [],
                "domain_contexts": [
                    {
                        "domain_id": "economic",
                        "facts": {"tasks": ["trend"], "datasets": ["economic"]},
                        "analysis_intent": {
                            "operations": [{"id": "analysis", "kind": "trend", "output_kinds": ["timeseries", "metrics"]}],
                            "data_kinds": ["timeseries", "metrics"],
                            "fact_refs": ["indicator", "regions"],
                            "source": "domain",
                        },
                    },
                    {
                        "domain_id": "gis",
                        "facts": {"tasks": ["roads"], "datasets": ["roads"]},
                        "analysis_intent": {
                            "operations": [{"id": "analysis", "kind": "spatial_operation", "output_kinds": ["vector"]}],
                            "data_kinds": ["vector"],
                            "fact_refs": ["admin_name"],
                            "source": "domain",
                        },
                    },
                ],
            }
        )
        domains = envelope["request_facts"]["domains"]
        self.assertEqual(domains[0]["analysis_intent"]["operations"][0]["kind"], "trend")
        self.assertEqual(domains[1]["analysis_intent"]["data_kinds"], ["vector"])

    def test_domain_catalogs_declare_supported_operations(self):
        economic = EconomicDomainPack()
        gis = GisDomainPack()
        economic_intent = economic.analysis_intent(
            "分析地区生产总值趋势",
            economic.extract_request_facts("分析地区生产总值趋势"),
        )
        gis_intent = gis.analysis_intent(
            "查询洪山区道路并做最近距离分析",
            gis.extract_request_facts("查询洪山区道路并做最近距离分析"),
        )
        self.assertEqual(economic_intent["operations"][0]["kind"], "trend")
        self.assertEqual(gis_intent["operations"][0]["kind"], "spatial_operation")
        economic_capabilities = economic.capability_catalog(environment="memory")["capabilities"]
        gis_capabilities = gis.capability_catalog(environment="memory")["capabilities"]
        self.assertIn("trend", next(item for item in economic_capabilities if item["id"] == "economic_indicator_trend")["analysis_operations"])
        self.assertIn("spatial_operation", next(item for item in gis_capabilities if item["id"] == "vector_operation")["analysis_operations"])

    def test_selected_capability_must_support_explicit_component_operation(self):
        context = {
            "capability_index": [
                {
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_trend",
                    "available": True,
                    "analysis_operations": ["trend", "evidence"],
                }
            ]
        }
        plan = normalize_composite_plan(
            {
                "outcome": "success",
                "goal": "趋势",
                "message": "",
                "components": [{
                    "component_id": "trend",
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_trend",
                    "request": "分析趋势",
                    "depends_on": [],
                    "required": True,
                    "analysis_operations": ["trend"],
                }],
            },
            request="分析趋势",
            context=context,
            planner_source="llm",
        )
        self.assertEqual(plan["components"][0]["analysis_operations"], ["trend"])
        with self.assertRaises(CompositePlannerError) as raised:
            normalize_composite_plan(
                {
                    "outcome": "success",
                    "goal": "趋势",
                    "message": "",
                    "components": [{
                        "component_id": "trend",
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_trend",
                        "request": "分析趋势",
                        "depends_on": [],
                        "required": True,
                        "analysis_operations": ["spatial_operation"],
                    }],
                },
                request="分析趋势",
                context=context,
                planner_source="llm",
            )
        self.assertEqual(raised.exception.code, "capability_operation_mismatch")

    def test_explicit_component_operation_requires_catalog_declaration(self):
        with self.assertRaises(CompositePlannerError) as raised:
            normalize_composite_plan(
                {
                    "outcome": "success",
                    "goal": "查询",
                    "message": "",
                    "components": [{
                        "component_id": "query",
                        "domain_id": "text",
                        "capability_id": "text_summary",
                        "request": "总结文本",
                        "depends_on": [],
                        "required": True,
                        "analysis_operations": ["query"],
                    }],
                },
                request="总结文本",
                context={"capability_index": [{"domain_id": "text", "capability_id": "text_summary", "available": True}]},
                planner_source="llm",
            )
        self.assertEqual(raised.exception.code, "capability_operation_undeclared")

    def test_intent_evidence_survives_composite_view_projection(self):
        projection = build_composite_view_projection(
            {
                "status": "COMPLETED",
                "composite": {
                    "state": "completed",
                    "request": {"fingerprint": "sha256:request"},
                    "components": [],
                    "evidence": {},
                },
                "planner_evidence": {
                    "analysis_intents": [
                        {
                            "domain_id": "economic",
                            "intent": {
                                "operations": [
                                    {"kind": "trend", "output_kinds": ["timeseries", "metrics"]}
                                ],
                                "data_kinds": ["timeseries", "metrics"],
                                "source": "domain",
                            },
                        },
                        {
                            "domain_id": "ignored",
                            "intent": {"operations": ["not_registered"]},
                        },
                    ]
                },
            }
        )
        self.assertEqual(len(projection["planning"]["analysis_intents"]), 1)
        self.assertEqual(
            projection["planning"]["analysis_intents"][0]["intent"]["operations"][0]["kind"],
            "trend",
        )
        safe = _safe_planning_evidence(
            {
                "analysis_intents": [
                    projection["planning"]["analysis_intents"][0],
                    {"domain_id": "bad", "intent": {"operations": ["unknown"]}},
                ]
            }
        )
        self.assertEqual(len(safe["analysis_intents"]), 1)

    def test_provider_plan_without_result_type_fails_before_execution(self):
        class MissingResultTypeClient:
            def complete_json(self, messages, schema):
                return {
                    "goal": "查询栅格",
                    "steps": [{"id": "read", "tool": "get_raster_metadata", "args": {}}],
                }

        with self.assertRaises(PlanningError):
            LLMPlanner(MissingResultTypeClient(), ["get_raster_metadata"]).plan("查询栅格")


if __name__ == "__main__":
    unittest.main()
