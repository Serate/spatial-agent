"""Compact M308-A contracts for an open 3+ component vertical slice."""

from __future__ import annotations

import unittest

from agent.answer_generation import build_composite_answer_context
from agent.application.composite import CompositeApplication
from agent.application.composite_planning import CompositePlanningApplication
from agent.application.composite_contract import build_composite_result_contract
from agent.application.composite_planner import ReplayCompositePlanner
from agent.application.composite_view import build_composite_view_projection
from agent.runtime_core.composite_taskplan import CompositeTaskPlanBridge
from agent.runtime_core.preview import _merge_component_handoff_constraints


def _task_plan(tool: str, result_type: str) -> dict[str, object]:
    return {
        "goal": "执行一个分析组件",
        "steps": [
            {"id": "step", "tool": tool, "args": {}, "depends_on": []}
        ],
        "output": {"type": result_type},
        "assumptions": [],
    }


CAPABILITY_CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m308-a-context",
    "domain_ids": ["gis", "economic", "indicators"],
    "domain_contexts": [
        {"domain_id": "gis", "facts": {}, "workflow": {}},
        {"domain_id": "economic", "facts": {}, "workflow": {}},
        {"domain_id": "indicators", "facts": {}, "workflow": {}},
    ],
    "capability_index": [
        {
            "domain_id": "gis",
            "capability_id": "gis.vector",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
            "tools": ["gis-vector-tool"],
            "result_types": ["vector_result"],
            "output_profiles": [{"kinds": ["vector"]}],
        },
        {
            "domain_id": "economic",
            "capability_id": "economic.raster",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
            "tools": ["economic-raster-tool"],
            "result_types": ["raster_result"],
            "output_profiles": [{"kinds": ["raster"]}],
        },
        {
            "domain_id": "indicators",
            "capability_id": "indicators.trend",
            "available": True,
            "plan_mode": "workflow",
            "execution_ready": True,
            "tools": ["indicator-trend-tool"],
            "result_types": ["timeseries_result"],
            "output_profiles": [{"kinds": ["timeseries"]}],
        },
    ],
}


def _three_component_payload() -> dict[str, object]:
    return {
        "outcome": "success",
        "goal": "组合空间、栅格与趋势分析",
        "message": "",
        "components": [
            {
                "component_id": "shape",
                "domain_id": "gis",
                "capability_id": "gis.vector",
                "request": "生成空间范围摘要",
                "depends_on": [],
                "required": True,
                "workflow": {
                    "allowed_tools": ["gis-vector-tool"],
                    "result_types": ["vector_result"],
                    "task_plan": _task_plan("gis-vector-tool", "vector_result"),
                },
            },
            {
                "component_id": "surface",
                "domain_id": "economic",
                "capability_id": "economic.raster",
                "request": "生成栅格指标摘要",
                "depends_on": [],
                "required": True,
                "workflow": {
                    "allowed_tools": ["economic-raster-tool"],
                    "result_types": ["raster_result"],
                    "task_plan": _task_plan("economic-raster-tool", "raster_result"),
                },
            },
            {
                "component_id": "trend",
                "domain_id": "indicators",
                "capability_id": "indicators.trend",
                "request": "结合空间与栅格结果分析趋势",
                "depends_on": ["shape", "surface"],
                "required": True,
                "inputs": [
                    {
                        "name": "空间摘要",
                        "source": {"component_id": "shape", "path": "result.items"},
                        "accepted_kinds": ["vector"],
                        "required": True,
                    },
                    {
                        "name": "栅格摘要",
                        "source": {"component_id": "surface", "path": "result.summary"},
                        "accepted_kinds": ["raster"],
                        "required": True,
                    },
                ],
                "workflow": {
                    "allowed_tools": ["indicator-trend-tool"],
                    "result_types": ["timeseries_result"],
                    "task_plan": _task_plan("indicator-trend-tool", "timeseries_result"),
                },
            },
        ],
    }


class _ContextBuilder:
    def build(self, request, *, planner, backend, domain_ids=None):
        del request, planner, backend, domain_ids
        return CAPABILITY_CONTEXT


class _PlanningHost:
    def select(self, domain_id, *, source="automatic"):
        del source
        if domain_id not in {"gis", "economic", "indicators"}:
            raise ValueError("domain is not enabled")
        return domain_id


class _InputAwareService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        plan = kwargs["validated_plan"]
        result_type = plan.output["type"]
        profile = {
            "vector_result": ("vector", {"items": [{"id": "shape-1"}]}),
            "raster_result": ("raster", {"summary": {"value": 3}}),
            "timeseries_result": ("timeseries", {"series": [{"value": 3}]}),
        }[result_type]
        kind, facts = profile
        return {
            "status": "COMPLETED",
            "result": {
                "type": result_type,
                "data_profile": {"primary": kind, "kinds": [kind]},
                "answer": f"{kind} 结果已完成。",
                **facts,
            },
        }


class _InputAwareHost(_PlanningHost):
    def __init__(self):
        self.service_instance = _InputAwareService()

    def service(self, selection):
        if selection not in {"gis", "economic", "indicators"}:
            raise ValueError("domain is not enabled")
        return self.service_instance


class _DiscoveryWorkflowService:
    def __init__(self):
        self.workflow = None

    def resolve_capability_selection(self, capability_id, *, request_facts=None, selection=None):
        del request_facts, selection
        if capability_id != "economic_indicator_discovery":
            return None
        return {"template_id": "economic_discovery", "constraints": {}}

    def preview(self, request, **kwargs):
        del request
        self.workflow = kwargs.get("workflow")
        return {
            "status": "PLANNED",
            "plan": {
                "goal": "发现经济指标",
                "steps": [
                    {"id": "discover", "tool": "economic_indicator_discovery", "args": {}, "depends_on": []}
                ],
                "output": {"type": "economic_catalog_result"},
            },
        }


class _DiscoveryWorkflowHost(_PlanningHost):
    def __init__(self):
        self.service_instance = _DiscoveryWorkflowService()

    def service(self, selection):
        if selection != "economic":
            raise ValueError("unknown domain")
        return self.service_instance


class M308OpenCompositionContractTests(unittest.TestCase):
    def test_component_handoff_only_merges_declared_workflow_constraints(self):
        workflow = {
            "template_id": "economic_discovery",
            "constraints": {},
        }

        merged = _merge_component_handoff_constraints(
            workflow,
            {
                "dataset": "wuhan_hongshan_economic_indicators",
                "indicator": "gdp_total",
                "regions": ["洪山区"],
            },
        )

        self.assertEqual(merged, workflow)

    def test_context_workflow_does_not_override_capability_specific_discovery_workflow(self):
        host = _DiscoveryWorkflowHost()
        bridge = CompositeTaskPlanBridge(host=host)
        result = bridge.bridge(
            [
                {
                    "component_id": "economic-catalog",
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_discovery",
                    "request": "列出可用经济指标",
                }
            ],
            context={
                "capability_index": [
                    {
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_discovery",
                        "available": True,
                        "tools": ["economic_indicator_discovery"],
                        "result_types": ["economic_catalog_result"],
                    }
                ],
                "domain_contexts": [
                    {
                        "domain_id": "economic",
                        "facts": {},
                        "workflow": {
                            "selected_capability_id": "economic_indicator_discovery",
                            "workflow_template_id": "economic_discovery",
                            "constraints": {
                                "dataset": "wuhan_hongshan_economic_indicators",
                                "indicator": "gdp_total",
                                "regions": ["洪山区"],
                            },
                        },
                    }
                ],
                "workflow_index": [
                    {
                        "domain_id": "economic",
                        "workflow_id": "economic_discovery",
                        "allowed_tools": ["economic_indicator_discovery"],
                        "result_types": ["economic_catalog_result"],
                    }
                ],
            },
            planner="rule",
            backend="local",
        )

        self.assertEqual(result["state"], "accepted")
        self.assertEqual(host.service_instance.workflow, {"template_id": "economic_discovery", "constraints": {}})

    def test_three_components_share_canonical_taskplan_and_binding_gates(self):
        planner = ReplayCompositePlanner(_three_component_payload())
        application = CompositePlanningApplication(
            host=_PlanningHost(),
            projector=object(),
            planner=planner,
            composite_runs=object(),
            context_builder=_ContextBuilder(),
        )

        prepared = application.prepare(
            "请组合分析空间范围、栅格指标和趋势",
            planner_name="replay",
            backend="memory",
            domain_ids=["gis", "economic", "indicators"],
        )

        self.assertEqual(prepared["status"], "PLANNED")
        self.assertEqual(
            [item["component_id"] for item in prepared["request"]["components"]],
            ["shape", "surface", "trend"],
        )
        self.assertEqual(prepared["task_plan_bridge"]["state"], "accepted")
        self.assertEqual(prepared["task_plan_bridge"]["materialized_count"], 3)
        self.assertEqual(prepared["execution_binding"]["state"], "validated")
        self.assertEqual(
            prepared["execution_binding"]["component_ids"],
            ["shape", "surface", "trend"],
        )
        self.assertEqual(
            prepared["execution_binding"]["components"][2]["depends_on"],
            ["shape", "surface"],
        )

    def test_three_components_execute_with_bounded_typed_input_handoff(self):
        planner = ReplayCompositePlanner(_three_component_payload())
        planning_host = _PlanningHost()
        prepared = CompositePlanningApplication(
            host=planning_host,
            projector=object(),
            planner=planner,
            composite_runs=object(),
            context_builder=_ContextBuilder(),
        ).prepare(
            "请组合分析空间范围、栅格指标和趋势",
            planner_name="replay",
            backend="memory",
            domain_ids=["gis", "economic", "indicators"],
        )
        self.assertEqual(prepared["status"], "PLANNED")

        host = _InputAwareHost()
        response = CompositeApplication(
            host=host,
            require_execution_binding=True,
        ).run(
            prepared["request"],
            run_id="m308-execution",
            execution_binding=getattr(prepared, "execution_binding"),
        )

        self.assertEqual(response["status"], "COMPLETED")
        self.assertEqual(response["result"]["composite"]["state"], "completed")
        self.assertEqual(len(host.service_instance.calls), 3)
        trend_inputs = host.service_instance.calls[2]["component_inputs"]
        self.assertEqual(trend_inputs["state"], "ready")
        self.assertEqual(
            [item["name"] for item in trend_inputs["items"]],
            ["空间摘要", "栅格摘要"],
        )
        self.assertEqual(response["components"][2]["input_evidence"]["state"], "delivered")
        self.assertEqual(
            response["result"]["composite"]["evidence"]["component_evidence"][2]["input_state"],
            "delivered",
        )

    def test_missing_or_drifting_upstream_output_blocks_only_consumer(self):
        from agent.application.composite import CompositeApplication

        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "校验上游输出",
            "components": [
                {"component_id": "source", "domain_id": "gis", "request": "上游"},
                {
                    "component_id": "consumer",
                    "domain_id": "economic",
                    "request": "下游",
                    "depends_on": ["source"],
                    "inputs": [
                        {
                            "name": "上游数据",
                            "source": {"component_id": "source", "path": "result.items"},
                            "accepted_kinds": ["vector"],
                            "required": True,
                        }
                    ],
                },
            ],
        }

        class _Service:
            def __init__(self, result):
                self.result = result
                self.calls = 0

            def run(self, **kwargs):
                del kwargs
                self.calls += 1
                return self.result

        source = _Service(
            {
                "status": "COMPLETED",
                "result": {
                    "type": "vector_result",
                    "data_profile": {"primary": "vector", "kinds": ["vector"]},
                },
            }
        )
        consumer = _Service(
            {
                "status": "COMPLETED",
                "result": {
                    "type": "metrics_result",
                    "data_profile": {"primary": "metrics", "kinds": ["metrics"]},
                },
            }
        )

        class _Host:
            def select(self, domain_id, *, source="explicit"):
                del source
                return domain_id

            def service(self, selection):
                return {"gis": source, "economic": consumer}[selection]

        response = CompositeApplication(host=_Host()).run(request)
        by_id = {item["component_id"]: item for item in response["components"]}

        self.assertEqual(by_id["source"]["state"], "completed")
        self.assertEqual(by_id["consumer"]["state"], "blocked")
        self.assertEqual(by_id["consumer"]["error_code"], "composition_input_result_missing")
        self.assertEqual(consumer.calls, 0)

    def test_mixed_profiles_are_aggregated_without_domain_specific_projection(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "混合结果",
            "components": [
                {"component_id": "vector", "domain_id": "gis", "request": "矢量"},
                {"component_id": "raster", "domain_id": "gis", "request": "栅格"},
                {"component_id": "metrics", "domain_id": "economic", "request": "指标"},
                {"component_id": "trend", "domain_id": "indicators", "request": "趋势"},
            ],
        }
        profiles = {
            "vector": ("gis", "vector_result", "vector", "map"),
            "raster": ("gis", "raster_result", "raster", "raster"),
            "metrics": ("economic", "metrics_result", "metrics", "table"),
            "trend": ("indicators", "timeseries_result", "timeseries", "chart"),
        }
        children = {}
        for component_id, (domain_id, result_type, kind, panel_id) in profiles.items():
            children[component_id] = {
                "domain_id": domain_id,
                "status": "COMPLETED",
                "result": {
                    "type": result_type,
                    "data_profile": {"primary": kind, "kinds": [kind]},
                    "answer": f"{component_id} 已完成。",
                    "views": {"panels": {panel_id: {"kind": panel_id, "title": component_id}}},
                },
            }

        result = build_composite_result_contract(request, children, run_id="m308-mixed")
        projection = build_composite_view_projection(result)

        self.assertEqual(result["composite"]["state"], "completed")
        self.assertEqual(
            result["data_profile"]["kinds"],
            ["composite", "vector", "raster", "metrics", "timeseries"],
        )
        self.assertEqual(len(projection["sections"]) - 1, 4)
        self.assertTrue({"map", "raster", "table", "chart"}.issubset(
            {view["kind"] for view in projection["views"]}
        ))

    def test_optional_component_failure_preserves_completed_facts_and_limitation(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "部分失败组合分析",
            "components": [
                {"component_id": "space", "domain_id": "gis", "request": "空间"},
                {
                    "component_id": "trend",
                    "domain_id": "indicators",
                    "request": "趋势",
                    "required": False,
                },
            ],
        }
        children = {
            "space": {
                "domain_id": "gis",
                "status": "COMPLETED",
                "result": {
                    "type": "vector_result",
                    "data_profile": {"primary": "vector", "kinds": ["vector"]},
                    "answer": "空间结果已完成。",
                },
            },
            "trend": {
                "domain_id": "indicators",
                "status": "FAILED",
                "error": "趋势数据暂不可用",
            },
        }

        result = build_composite_result_contract(request, children, run_id="m308-partial")
        projection = build_composite_view_projection(result)

        self.assertEqual(result["composite"]["state"], "partial")
        self.assertEqual(result["composite"]["evidence"]["completed_component_ids"], ["space"])
        self.assertEqual(result["composite"]["evidence"]["failed_component_ids"], ["trend"])
        self.assertIn("空间结果已完成。", projection["answer"]["key_findings"])
        self.assertTrue(projection["answer"]["limitations"])
        self.assertTrue(projection["answer"]["next_steps"])

    def test_answer_context_uses_facts_but_not_internal_composite_identity(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "事实摘要",
            "components": [
                {"component_id": "space", "domain_id": "gis", "request": "空间"},
            ],
        }
        result = build_composite_result_contract(
            request,
            {
                "space": {
                    "domain_id": "gis",
                    "status": "COMPLETED",
                    "result": {
                        "type": "vector_result",
                        "data_profile": {"primary": "vector", "kinds": ["vector"]},
                        "answer": "空间结果已完成。",
                    },
                }
            },
            run_id="m308-answer",
        )
        context = build_composite_answer_context(result)

        self.assertNotIn("request_fingerprint", context)
        self.assertNotIn("memory://", str(context))
        self.assertIn("空间结果已完成。", str(context))


if __name__ == "__main__":
    unittest.main()
