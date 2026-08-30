"""Compact contracts for the cross-Domain capability Host."""

from __future__ import annotations

import unittest

from agent.domain_registry import DomainEntry, DomainRegistry
from agent.errors import ToolError
from agent.planner_context import project_planner_sections
from agent.general_capability_host import (
    GeneralCapabilityHost,
    GeneralCapabilityHostError,
)
from agent.runtime_factory import build_general_runtime
from agent.tools import ToolRegistry


def _definition(name: str) -> dict:
    return {
        "name": name,
        "description": "bounded test tool",
        "side_effect": "none",
        "input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"result_ref": {"type": "string"}},
        },
    }


class _Provider:
    def __init__(self, provider_id: str, tool_name: str, *, status: str = "ready"):
        self.provider_id = provider_id
        self.tool_name = tool_name
        self.status = status
        self.calls = []

    def definitions(self):
        return {self.tool_name: _definition(self.tool_name)}

    def health(self):
        return {"status": self.status, "checks": [{"name": "fixture", "status": "passed"}]}

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return {"value": arguments["value"], "result_ref": "fixture://" + self.tool_name}


class _ResultRegistry:
    def __init__(self, result_type: str):
        self.result_type = result_type

    def as_context(self):
        return {"result_types": [{"type": self.result_type, "title": self.result_type}]}


class _Pack:
    def __init__(self, domain_id: str, tool_name: str, *, provider=None, result_type=None):
        self.domain_id = domain_id
        self.tool_name = tool_name
        self.provider = provider
        self.result_type = result_type or domain_id + "_result"
        self.preflight_calls = []

    def default_permissions(self):
        return {self.domain_id + ":read"}

    def tool_provider_info(self, *, backend_name="memory", root=None):
        del backend_name, root
        return {"id": self.domain_id + "-provider", "tool_count": 1}

    def tool_provider(self, *, backend_name="memory", root=None):
        del backend_name, root
        if isinstance(self.provider, Exception):
            raise self.provider
        return self.provider

    def capability_catalog(self, *, environment="unknown"):
        return {
            "version": "1.0",
            "domain_id": self.domain_id,
            "environment": environment,
            "capabilities": [{
                "id": self.domain_id + "_capability",
                "label": self.domain_id,
                "datasets": [self.domain_id + "_data"],
                "tools": [self.tool_name],
                "result_types": [self.result_type],
                "environments": [environment],
                "available": True,
            }],
            "capability_descriptors": [
                {
                    "schema_version": "spatial-agent.capability-descriptor.v1",
                    "catalog_version": "fixture-1",
                    "domain_id": self.domain_id,
                    "capability_id": self.domain_id + "_capability",
                    "label": self.domain_id,
                    "summary": "fixture capability",
                    "inputs": {"facts": [], "datasets": [self.domain_id + "_data"]},
                    "outputs": {"result_types": [self.result_type], "geometry": "none"},
                    "preconditions": {
                        "environments": [environment],
                        "datasets": [self.domain_id + "_data"],
                        "required_facts": [],
                        "data_readiness": "required",
                    },
                    "evidence_requirements": {
                        "required": ["execution_receipt"],
                        "dataset_provenance": True,
                        "result_profiles": [self.result_type],
                        "geometry": "none",
                        "declared_by_domain": True,
                    },
                    "execution": {"tools": [self.tool_name], "operations": []},
                    "cost_hint": {
                        "class": "low",
                        "estimated_tool_count": 1,
                        "estimated_step_count": 1,
                    },
                    "availability": {
                        "available": True,
                        "mode": "native",
                        "status": "ready",
                        "reason": "fixture",
                    },
                }
            ],
            "dataset_tools": {self.domain_id + "_data": [self.tool_name]},
            "available_dataset_tools": {self.domain_id + "_data": [self.tool_name]},
            "dataset_groups": {"core": [self.domain_id + "_data"]},
            "workflow_templates": {},
            "actions": {"actions": []},
        }

    def result_registry(self):
        return _ResultRegistry(self.result_type)

    def preflight_tool(self, tool, arguments, completed_results, **kwargs):
        self.preflight_calls.append((tool, dict(arguments), dict(completed_results), kwargs))


def _registry(*packs):
    return DomainRegistry({
        pack.domain_id: DomainEntry(
            domain_id=pack.domain_id,
            label=pack.domain_id,
            description="fixture",
            factory=lambda pack=pack: pack,
        )
        for pack in packs
    })


class M329CapabilityHostTests(unittest.TestCase):
    def test_aggregate_owner_dispatch_and_preflight(self):
        alpha_provider = _Provider("alpha-provider", "alpha_tool")
        beta_provider = _Provider("beta-provider", "beta_tool")
        alpha = _Pack("alpha", "alpha_tool", provider=alpha_provider)
        beta = _Pack("beta", "beta_tool", provider=beta_provider)
        host = GeneralCapabilityHost(
            registry=_registry(alpha, beta),
            domain_ids=("beta", "alpha"),
        )

        self.assertEqual(host.names, ("alpha_tool", "beta_tool"))
        self.assertEqual(host.owner_map(), {"alpha_tool": "alpha", "beta_tool": "beta"})
        registry = ToolRegistry.from_provider(host)
        self.assertEqual(registry.invoke("beta_tool", {"value": "ok"})["value"], "ok")
        host.preflight_tool(
            "alpha_tool",
            {"value": "ok"},
            {"previous": {"status": "ready"}},
            required_datasets=("alpha_data",),
            require_dependency_evidence=True,
        )
        self.assertEqual(beta_provider.calls, [("beta_tool", {"value": "ok"})])
        self.assertEqual(alpha.preflight_calls[0][0], "alpha_tool")
        catalog = host.capability_catalog()
        self.assertEqual(catalog["domain_ids"], ["alpha", "beta"])
        self.assertEqual(catalog["tool_owners"]["alpha_tool"], "alpha")
        self.assertEqual(catalog["permissions"], ["alpha:read", "beta:read"])
        self.assertEqual(host.health()["status"], "ready")

    def test_one_provider_failure_is_degraded_and_keeps_other_owner(self):
        alpha = _Pack("alpha", "alpha_tool", provider=_Provider("alpha-provider", "alpha_tool"))
        beta = _Pack("beta", "beta_tool", provider=RuntimeError("fixture unavailable"))
        host = GeneralCapabilityHost(registry=_registry(alpha, beta))

        self.assertEqual(host.health()["status"], "degraded")
        self.assertEqual(host.capability_catalog()["health_status"], "degraded")
        descriptor = host.capability_catalog()["capability_descriptors"][1]
        self.assertIsInstance(descriptor["availability"], dict)
        self.assertFalse(descriptor["availability"]["available"])
        projected = project_planner_sections(
            capability_discovery={},
            capability_catalog=host.capability_catalog(),
            workflow_selection={},
            workflow_templates={},
        )
        self.assertEqual(
            projected["capability_catalog"]["capability_descriptors"][1]["availability"]["mode"],
            "unavailable",
        )
        self.assertEqual(host.invoke("alpha_tool", {"value": "works"})["value"], "works")
        self.assertEqual(host.owner_for("beta_tool"), "beta")
        with self.assertRaises(ToolError) as caught:
            host.invoke("beta_tool", {"value": "blocked"})
        self.assertEqual(caught.exception.code, "provider_initialization_unavailable")

    def test_tool_capability_and_result_conflicts_fail_closed(self):
        alpha = _Pack("alpha", "shared_tool", provider=_Provider("alpha-provider", "shared_tool"), result_type="shared_result")
        beta = _Pack("beta", "shared_tool", provider=_Provider("beta-provider", "shared_tool"), result_type="other_result")
        with self.assertRaisesRegex(GeneralCapabilityHostError, "conflicting registered identity") as caught:
            GeneralCapabilityHost(registry=_registry(alpha, beta))
        self.assertEqual(caught.exception.code, "tool_name_conflict")

        gamma = _Pack("gamma", "gamma_tool", provider=_Provider("gamma-provider", "gamma_tool"), result_type="shared_result")
        with self.assertRaisesRegex(GeneralCapabilityHostError, "conflicting registered identity") as caught:
            GeneralCapabilityHost(registry=_registry(alpha, gamma))
        self.assertEqual(caught.exception.code, "result_type_conflict")

    def test_context_fingerprint_is_stable_and_catalog_is_detached(self):
        alpha = _Pack("alpha", "alpha_tool", provider=_Provider("alpha-provider", "alpha_tool"))
        registry = _registry(alpha)
        first = GeneralCapabilityHost(registry=registry)
        second = GeneralCapabilityHost(registry=registry)
        self.assertEqual(first.context_fingerprint, second.context_fingerprint)
        catalog = first.capability_catalog()
        catalog["capabilities"][0]["label"] = "changed"
        self.assertNotEqual(first.capability_catalog()["capabilities"][0]["label"], "changed")

    def test_general_runtime_uses_the_aggregate_host(self):
        runtime = build_general_runtime("rule", "memory")
        result = runtime.run("请解释什么是坐标系")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.domain_id, "general")
        self.assertEqual(result.request_mode["mode"], "answer")
        self.assertEqual(runtime._registry.provider_info()["id"], "general-capability-host")


if __name__ == "__main__":
    unittest.main()
