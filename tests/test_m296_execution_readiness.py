import unittest
import tempfile
from pathlib import Path

from agent.application.composite_planning import CompositeCapabilityProjector
from agent.composite_request_context import CompositeRequestContextBuilder
from agent.service import AgentService
from agent.runtime_core.analysis_discovery import AnalysisDiscoveryGateway
from agent.runtime_core.plan_completeness import assess_catalog_consistency


def _contract(*, tools=("query",), results=("metrics",), status="valid"):
    return {
        "schema_version": "spatial-agent.execution-contract.v1",
        "status": status,
        "tool_names": list(tools),
        "tool_definitions": {name: {"input_schema": {"type": "object"}} for name in tools},
        "result_type_ids": list(results),
    }


def _domain(*, workflows, contract=None, tools=("query",), results=("metrics",)):
    value = {
        "domain_id": "demo",
        "capabilities": [
            {
                "id": "summary",
                "tools": list(tools),
                "result_types": list(results),
            }
        ],
        "workflows": workflows,
    }
    if contract is not None:
        value["execution_contract"] = contract
    return value


class M296ExecutionReadinessTests(unittest.TestCase):
    def test_service_exposes_domain_capability_workflow_resolution(self):
        class _Runtime:
            def resolve_capability_selection(self, capability_id, **kwargs):
                return {
                    "template_id": capability_id,
                    "constraints": dict(kwargs.get("request_facts") or {}),
                }

        runtime = _Runtime()
        with tempfile.TemporaryDirectory() as root:
            service = AgentService(
                runtime_factory=lambda planner, backend, **kwargs: runtime,
                state_db_path=str(Path(root) / "runs.db"),
            )
            try:
                workflow = service.resolve_capability_selection(
                    "economic_indicator_latest",
                    request_facts={"indicator": "gdp_total"},
                    planner="rule",
                    backend="memory",
                )
            finally:
                service.close()
        self.assertEqual(workflow["template_id"], "economic_indicator_latest")

    def test_projector_uses_runtime_data_readiness_over_static_unknown(self):
        class _Service:
            def capabilities(self, **kwargs):
                del kwargs
                return {
                    "domain_id": "demo",
                    "environment": "local",
                    "data_readiness": {"status": "unknown"},
                    "capabilities": [
                        {
                            "id": "summary",
                            "available": True,
                            "tools": ["query"],
                            "result_types": ["metrics"],
                        }
                    ],
                }

            def workflow_contract(self, **kwargs):
                del kwargs
                return {
                    "catalog": {
                        "summary": {
                            "id": "summary",
                            "allowed_tools": ["query"],
                            "result_types": ["metrics"],
                            "step_blueprint": [{"id": "query", "tool": "query"}],
                        }
                    },
                    "known_tools": ["query"],
                    "known_result_types": ["metrics"],
                }

            def execution_contract(self, **kwargs):
                del kwargs
                return _contract()

            def runtime_capabilities(self, **kwargs):
                del kwargs
                return {"data_readiness": "ready"}

        class _Host:
            def catalog(self):
                return {"domain_ids": ["demo"], "domains": [{"id": "demo"}]}

            def select(self, domain_id, *, source="automatic"):
                del source
                return domain_id

            def service(self, selection):
                del selection
                return _Service()

        context = CompositeCapabilityProjector(_Host()).project(
            planner="rule", backend="local", domain_ids=["demo"]
        )
        self.assertEqual(context["domains"][0]["data_readiness"]["status"], "ready")

    def test_request_context_preserves_registered_workflow_index(self):
        class _Service:
            def capabilities(self, **kwargs):
                del kwargs
                return {
                    "domain_id": "demo",
                    "environment": "local",
                    "data_readiness": {"status": "ready"},
                    "capabilities": [
                        {
                            "id": "summary",
                            "available": True,
                            "tools": ["query"],
                            "result_types": ["metrics"],
                        }
                    ],
                }

            def workflow_contract(self, **kwargs):
                del kwargs
                return {
                    "catalog": {
                        "summary": {
                            "id": "summary",
                            "allowed_tools": ["query"],
                            "result_types": ["metrics"],
                        }
                    },
                    "known_tools": ["query"],
                    "known_result_types": ["metrics"],
                }

            def execution_contract(self, **kwargs):
                del kwargs
                return _contract()

            def runtime_capabilities(self, **kwargs):
                del kwargs
                return {"data_readiness": "ready"}

        class _Host:
            def catalog(self):
                return {"domain_ids": ["demo"], "domains": [{"id": "demo"}]}

            def select(self, domain_id, *, source="automatic"):
                del source
                return domain_id

            def service(self, selection):
                del selection
                return _Service()

        context = CompositeRequestContextBuilder(
            host=_Host(),
            catalog_projector=CompositeCapabilityProjector(_Host()),
        ).build("分析摘要", planner="rule", backend="local", domain_ids=["demo"])
        self.assertEqual(context["workflow_index"][0]["workflow_id"], "summary")

    def test_request_context_preserves_complete_tool_allowlist(self):
        tools = tuple(f"tool_{index}" for index in range(9))

        class _Service:
            def capabilities(self, **kwargs):
                del kwargs
                return {
                    "domain_id": "demo",
                    "environment": "local",
                    "data_readiness": {"status": "ready"},
                    "capabilities": [
                        {
                            "id": "summary",
                            "available": True,
                            "tools": list(tools),
                            "result_types": ["metrics"],
                        }
                    ],
                }

            def workflow_contract(self, **kwargs):
                del kwargs
                return {
                    "catalog": {
                        "summary": {
                            "id": "summary",
                            "allowed_tools": list(tools),
                            "result_types": ["metrics"],
                        }
                    },
                    "known_tools": list(tools),
                    "known_result_types": ["metrics"],
                }

            def execution_contract(self, **kwargs):
                del kwargs
                return _contract(tools=tools)

            def runtime_capabilities(self, **kwargs):
                del kwargs
                return {"data_readiness": "ready"}

        class _Host:
            def catalog(self):
                return {"domain_ids": ["demo"], "domains": [{"id": "demo"}]}

            def select(self, domain_id, *, source="automatic"):
                del source
                return domain_id

            def service(self, selection):
                del selection
                return _Service()

        host = _Host()
        context = CompositeRequestContextBuilder(
            host=host,
            catalog_projector=CompositeCapabilityProjector(host),
        ).build("分析摘要", planner="rule", backend="local", domain_ids=["demo"])
        candidate = context["capability_index"][0]
        self.assertEqual(candidate["tools"], list(tools))
        self.assertTrue(candidate["execution_ready"])

    def test_unknown_data_readiness_is_not_execution_ready(self):
        receipt = AnalysisDiscoveryGateway().discover(
            "分析摘要",
            planner="rule",
            backend="local",
            domain_ids=["demo"],
            domain_contexts=[
                {
                    "domain_id": "demo",
                    "discovery": {"state": "available"},
                    "workflow": {"state": "available"},
                    "data_readiness": {"status": "unknown"},
                }
            ],
            candidate_index=[
                {
                    "domain_id": "demo",
                    "capability_id": "summary",
                    "available": True,
                    "datasets": ["dataset"],
                    "missing_datasets": [],
                    "tools": ["query"],
                    "result_types": ["metrics"],
                    "workflow_ids": ["summary"],
                    "plan_mode": "task_plan",
                    "execution_readiness": "ready",
                    "execution_ready": True,
                }
            ],
        )

        candidate = receipt["candidates"][0]
        self.assertEqual(candidate["state"], "data_unavailable")
        self.assertFalse(candidate["execution_ready"])
        self.assertEqual(candidate["execution_reason_code"], "data_readiness_unknown")

    def test_valid_contract_closes_capability_to_execution(self):
        receipt = assess_catalog_consistency(
            {
                "domains": [
                    _domain(
                        workflows=[
                            {
                                "id": "summary",
                                "allowed_tools": ["query"],
                                "result_types": ["metrics"],
                                "steps": [{"id": "query", "tool": "query"}],
                            }
                        ],
                        contract=_contract(),
                        tools=("query", "buffer"),
                        results=("metrics", "vector"),
                    )
                ]
            }
        )

        binding = receipt["bindings"][0]
        self.assertEqual(binding["execution_readiness"], "ready")
        self.assertTrue(binding["execution_ready"])
        self.assertEqual(binding["execution_reason_code"], "execution_contract_valid")

    def test_missing_tool_or_result_is_schema_invalid(self):
        receipt = assess_catalog_consistency(
            {
                "domains": [
                    _domain(
                        workflows=[
                            {
                                "id": "summary",
                                "allowed_tools": ["query", "buffer"],
                                "result_types": ["metrics", "vector"],
                            }
                        ],
                        contract=_contract(),
                        tools=("query", "buffer"),
                        results=("metrics", "vector"),
                    )
                ]
            }
        )

        binding = receipt["bindings"][0]
        self.assertEqual(binding["execution_readiness"], "schema_invalid")
        self.assertFalse(binding["execution_ready"])
        self.assertEqual(binding["execution_reason_code"], "schema_invalid")
        self.assertEqual(binding["missing_tools"], ["buffer"])
        self.assertEqual(binding["missing_result_types"], ["vector"])

    def test_unbound_workflow_is_not_execution_ready(self):
        receipt = assess_catalog_consistency(
            {
                "domains": [
                    _domain(
                        workflows=[],
                        contract=_contract(),
                    )
                ]
            }
        )

        binding = receipt["bindings"][0]
        self.assertEqual(binding["plan_mode"], "unbound")
        self.assertEqual(binding["execution_readiness"], "workflow_unbound")
        self.assertFalse(binding["execution_ready"])

    def test_discovery_keeps_structural_failure_distinct_from_data_failure(self):
        receipt = AnalysisDiscoveryGateway().discover(
            "分析摘要",
            planner="rule",
            backend="memory",
            domain_ids=["demo"],
            domain_contexts=[
                {
                    "domain_id": "demo",
                    "discovery": {"state": "available"},
                    "workflow": {"state": "available"},
                    "data_readiness": {"status": "ready"},
                }
            ],
            candidate_index=[
                {
                    "domain_id": "demo",
                    "capability_id": "summary",
                    "available": True,
                    "datasets": [],
                    "missing_datasets": [],
                    "tools": ["query"],
                    "result_types": ["metrics"],
                    "workflow_ids": ["summary"],
                    "plan_mode": "task_plan",
                    "execution_readiness": "schema_invalid",
                    "execution_ready": False,
                    "execution_reason_code": "schema_invalid",
                }
            ],
        )

        self.assertEqual(receipt["state"], "capability_unavailable")
        self.assertEqual(receipt["reason_code"], "schema_invalid")
        self.assertEqual(receipt["candidates"][0]["state"], "schema_invalid")
        self.assertFalse(receipt["candidates"][0]["execution_ready"])


if __name__ == "__main__":
    unittest.main()
