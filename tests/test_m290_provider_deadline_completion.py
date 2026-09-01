import os
from tempfile import TemporaryDirectory
import unittest
from threading import Event
from unittest.mock import patch

from agent.application.composite_request_context import _unique_candidates
from agent.runtime_core.composite_taskplan import CompositeTaskPlanBridge
from agent.service import AgentService
from agent.sqlite_store import SQLiteConversationStore
from evaluation.live_provider_probe import run_composite_planning_probe
from scripts.live_provider_probe import _configure_composite_probe_environment


class _ProviderTimeoutApplication:
    def prepare(self, request, **kwargs):
        return {
            "status": "REJECTED",
            "error_code": "planner_provider_failed",
            "components": [],
            "planner_evidence": {
                "structured_output": {
                    "schema_version": "spatial-agent.provider-structured-output.v1",
                    "wire_api": "chat_completions",
                    "structured_mode": "json_schema",
                    "schema_enforced": True,
                    "source": "config",
                    "reason_code": "configured",
                    "status": "error",
                    "error_type": "timeout",
                    "attempts": 1,
                    "retries": 0,
                }
            },
        }


class _BlockingApplication:
    def __init__(self):
        self.started = Event()
        self.release = Event()

    def prepare(self, request, **kwargs):
        self.started.set()
        self.release.wait()
        return {"status": "PLANNED", "components": [{"component_id": "never-run"}]}


class _PreviewHost:
    def __init__(self):
        self.service_instance = None

    def select(self, domain_id, *, source="automatic"):
        return domain_id

    def service(self, selection):
        self.service_instance = _PreviewService()
        return self.service_instance


class _PreviewService:
    def __init__(self):
        self.planner = None
        self.workflow = None

    def resolve_capability_selection(
        self, capability_id, *, request_facts=None, selection=None
    ):
        del request_facts, selection
        if capability_id == "economic_indicator_latest":
            return {
                "template_id": "economic_latest",
                "constraints": {
                    "dataset": "wuhan_hongshan_economic_indicators",
                    "indicator": "gdp_total",
                    "regions": ["洪山区"],
                },
            }
        if capability_id == "economic_indicator_trend":
            return {
                "template_id": "economic_trend",
                "constraints": {"indicator": "gdp_total", "regions": ["洪山区"]},
            }
        return None

    def preview(self, request, **kwargs):
        self.planner = kwargs.get("planner")
        self.workflow = kwargs.get("workflow")
        workflow = kwargs.get("workflow") or {}
        result_type = (
            "economic_metrics_result"
            if workflow.get("template_id") == "economic_latest"
            else "economic_timeseries_result"
        )
        tool = (
            "economic_indicator_query"
            if workflow.get("template_id") == "economic_latest"
            else "economic_indicator_trend"
        )
        return {
            "status": "PLANNED",
            "plan": {
                "goal": "经济趋势",
                "steps": [
                    {
                        "id": "query",
                        "tool": tool,
                        "args": {},
                        "depends_on": [],
                    }
                ],
                "output": {"type": result_type},
            },
        }


class _SessionBoundPreviewHost:
    """Small host seam that reproduces the persistent session-domain guard."""

    def __init__(self, db_path):
        self._services = {
            domain_id: _SessionBoundPreviewService(domain_id, db_path)
            for domain_id in ("gis", "economic")
        }

    def select(self, domain_id, *, source="automatic"):
        return domain_id

    def service(self, selection):
        return self._services[selection]


class _SessionBoundPreviewService:
    def __init__(self, domain_id, db_path):
        self.domain_id = domain_id
        self.preview_session_ids = []
        self.store = SQLiteConversationStore(
            db_path,
            domain_id=domain_id,
            legacy_domain_id=domain_id,
        )

    def preview(self, request, **kwargs):
        session_id = kwargs["session_id"]
        self.preview_session_ids.append(session_id)
        self.store.ensure_session(session_id)
        if self.domain_id == "gis":
            tool = "get_raster_metadata"
            result_type = "raster_metadata_result"
        else:
            tool = "economic_indicator_query"
            result_type = "economic_timeseries_result"
        return {
            "status": "PLANNED",
            "plan": {
                "goal": request,
                "steps": [
                    {"id": "query", "tool": tool, "args": {}, "depends_on": []}
                ],
                "output": {"type": result_type},
            },
        }

    def resolve_capability_selection(
        self, capability_id, *, request_facts=None, selection=None
    ):
        del request_facts, selection
        if self.domain_id == "gis" and capability_id == "gis.summary":
            return {"template_id": "gis_summary", "constraints": {}}
        if self.domain_id == "economic" and capability_id == "economic_indicator_trend":
            return {
                "template_id": "economic_trend",
                "constraints": {"indicator": "gdp_total", "regions": ["洪山区"]},
            }
        return None


class M290ProviderDeadlineCompletionTests(unittest.TestCase):
    def test_component_preview_reuses_matching_domain_workflow_from_context(self):
        host = _PreviewHost()
        bridge = CompositeTaskPlanBridge(host=host)
        result = bridge.bridge(
            [
                {
                    "component_id": "economic-latest",
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_latest",
                    "request": "查询洪山区经济指标",
                }
            ],
            context={
                "capability_index": [
                    {
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_latest",
                        "tools": ["economic_indicator_query", "economic_source_evidence"],
                        "result_types": [
                            "economic_metrics_result",
                            "economic_evidence_result",
                        ],
                    }
                ],
                "domain_contexts": [
                    {
                        "domain_id": "economic",
                        "workflow": {
                            "selected_capability_id": "economic_indicator_latest",
                            "workflow_template_id": "economic_latest",
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
                        "workflow_id": "economic_latest",
                        "allowed_tools": [
                            "economic_indicator_query",
                            "economic_source_evidence",
                        ],
                        "result_types": [
                            "economic_metrics_result",
                            "economic_evidence_result",
                        ],
                    }
                ],
            },
            planner="openai",
            backend="local",
        )

        self.assertEqual(result["state"], "accepted")
        self.assertEqual(host.service_instance.planner, "rule")
        self.assertEqual(
            host.service_instance.workflow["template_id"], "economic_latest"
        )

    def test_composite_component_previews_isolate_session_domain_bindings(self):
        with TemporaryDirectory() as directory:
            host = _SessionBoundPreviewHost(os.path.join(directory, "state.db"))
            bridge = CompositeTaskPlanBridge(host=host)
            context = {
                "capability_index": [
                    {
                        "domain_id": "gis",
                        "capability_id": "gis.summary",
                        "tools": ["get_raster_metadata"],
                        "result_types": ["raster_metadata_result"],
                    },
                    {
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_trend",
                        "tools": ["economic_indicator_query", "economic_source_evidence"],
                        "result_types": ["economic_timeseries_result"],
                    },
                ],
                "workflow_index": [
                    {
                        "domain_id": "gis",
                        "workflow_id": "gis_summary",
                        "allowed_tools": ["get_raster_metadata"],
                        "result_types": ["raster_metadata_result"],
                    },
                    {
                        "domain_id": "economic",
                        "workflow_id": "economic_trend",
                        "allowed_tools": ["economic_indicator_query", "economic_source_evidence"],
                        "result_types": ["economic_timeseries_result"],
                    },
                ],
            }
            result = bridge.bridge(
                [
                    {
                        "component_id": "space",
                        "domain_id": "gis",
                        "capability_id": "gis.summary",
                        "request": "查询DEM栅格元数据",
                    },
                    {
                        "component_id": "economy",
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_trend",
                        "request": "查询经济趋势",
                    },
                ],
                context=context,
                planner="openai",
                backend="local",
            )

            self.assertEqual(result["state"], "accepted")
            self.assertEqual(result["materialized_count"], 2)
            self.assertEqual(
                [item["domain_id"] for item in result["components"]],
                ["gis", "economic"],
            )
            session_ids = [
                host._services[domain_id].preview_session_ids[0]
                for domain_id in ("gis", "economic")
            ]
            self.assertEqual(len(set(session_ids)), 2)
            self.assertTrue(all(value.startswith("composite-preview-") for value in session_ids))
            self.assertNotIn("default", session_ids)

    def test_llm_composite_materialization_does_not_nest_provider_preview(self):
        host = _PreviewHost()
        bridge = CompositeTaskPlanBridge(host=host)
        result = bridge.bridge(
            [
                {
                    "component_id": "economic-trend",
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_trend",
                    "request": "查询经济趋势",
                    "depends_on": [],
                    "required": True,
                }
            ],
            context={
                "capability_index": [
                    {
                        "domain_id": "economic",
                        "capability_id": "economic_indicator_trend",
                        "tools": ["economic_indicator_trend"],
                        "result_types": ["economic_timeseries_result"],
                    }
                ],
                "workflow_index": [
                    {
                        "domain_id": "economic",
                        "workflow_id": "economic_trend",
                        "allowed_tools": ["economic_indicator_trend"],
                        "result_types": ["economic_timeseries_result"],
                    }
                ],
            },
            planner="openai",
            backend="local",
        )

        self.assertEqual(result["state"], "accepted")
        self.assertEqual(host.service_instance.planner, "rule")

    def test_service_exposes_domain_facts_discovery_and_workflow_seams(self):
        service = AgentService(domain_id="economic")
        try:
            facts = service.extract_request_facts(
                "查询洪山区 gdp_total 2022至2025年度趋势"
            )
            discovery = service.discover(
                "查询洪山区 gdp_total 2022至2025年度趋势",
                facts,
            )
            workflow = service.select_workflow(discovery, facts)
        finally:
            service.close()

        self.assertEqual(facts.as_dict()["entities"]["indicator"], "gdp_total")
        self.assertIn("economic_indicator_trend", discovery.as_context_dict()["candidate_ids"])
        self.assertEqual(workflow["workflow_template_id"], "economic_trend")

    def test_composite_candidate_budget_keeps_later_domains_visible(self):
        values = [
            {"domain_id": "gis", "capability_id": "gis-" + str(index)}
            for index in range(16)
        ] + [
            {"domain_id": "economic", "capability_id": "economic-" + str(index)}
            for index in range(5)
        ]

        projected = _unique_candidates(values, 16)

        self.assertEqual(len(projected), 16)
        self.assertIn("economic", {item["domain_id"] for item in projected})
        self.assertEqual(
            [item["capability_id"] for item in projected if item["domain_id"] == "economic"],
            ["economic-" + str(index) for index in range(5)],
        )

    def test_lazy_composite_budget_forwards_timeout_retry_and_output_limit(self):
        with patch.dict(os.environ, {}, clear=False):
            _configure_composite_probe_environment(
                {
                    "timeout_seconds": 12.5,
                    "max_retries": 0,
                    "max_output_tokens": 1024,
                }
            )
            self.assertEqual(os.environ["OPENAI_TIMEOUT_SECONDS"], "12.5")
            self.assertEqual(os.environ["OPENAI_MAX_RETRIES"], "0")
            self.assertEqual(os.environ["OPENAI_MAX_OUTPUT_TOKENS"], "1024")

    def test_provider_timeout_is_distinct_and_never_creates_execution_run(self):
        report = run_composite_planning_probe(
            application=_ProviderTimeoutApplication(),
            request="查询 GIS 与指标",
            timeout_seconds=1,
            provider_timeout_seconds=0.8,
            max_retries=0,
        )

        self.assertFalse(report["passed"])
        self.assertEqual(report["error_plane"], "provider")
        self.assertEqual(report["error_code"], "planner_provider_failed")
        self.assertFalse(report["deadline"]["deadline_exceeded"])
        self.assertEqual(report["deadline"]["provider_timeout_seconds"], 0.8)
        self.assertEqual(report["deadline"]["max_retries"], 0)
        self.assertFalse(report["execution_run_created"])

    def test_harness_timeout_is_distinct_and_never_creates_execution_run(self):
        application = _BlockingApplication()
        report = run_composite_planning_probe(
            application=application,
            request="查询 GIS 与指标",
            timeout_seconds=0.05,
            provider_timeout_seconds=0.04,
            max_retries=0,
        )
        application.release.set()

        self.assertFalse(report["passed"])
        self.assertEqual(report["error_plane"], "harness")
        self.assertEqual(report["error_code"], "timeout")
        self.assertTrue(report["deadline"]["deadline_exceeded"])
        self.assertFalse(report["execution_run_created"])

    def test_provider_budget_cannot_exceed_harness_budget(self):
        with self.assertRaises(ValueError):
            run_composite_planning_probe(
                application=_ProviderTimeoutApplication(),
                request="查询 GIS 与指标",
                timeout_seconds=1,
                provider_timeout_seconds=2,
            )


if __name__ == "__main__":
    unittest.main()
