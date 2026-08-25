"""M276: explicit Composite coordinator execution seam."""

from __future__ import annotations

import unittest

from agent.application.composite import CompositeApplication, CompositeCoordinatorError
from agent.domain_registry import DomainSelectionError
from agent.domain_runtime_host import DomainRuntimeHost


def _request() -> dict:
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "组合分析空间与经济信息",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "request": "查询空间范围",
                "planner": "rule",
                "backend": "memory",
            },
            {
                "component_id": "economy",
                "domain_id": "economic",
                "request": "查询经济趋势",
                "planner": "rule",
                "backend": "memory",
                "depends_on": ["space"],
            },
            {
                "component_id": "independent",
                "domain_id": "indicators",
                "request": "查询独立指标",
                "planner": "rule",
                "backend": "memory",
            },
        ],
    }


class _Selection:
    def __init__(self, domain_id: str):
        self.domain_id = domain_id


class _Service:
    def __init__(self, domain_id: str, *, fail: bool = False):
        self.domain_id = domain_id
        self.fail = fail
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("private backend detail")
        return {
            "run_id": self.domain_id + "-run.json",
            "domain_id": self.domain_id,
            "status": "COMPLETED",
            "answer": self.domain_id + " 已完成。",
            "result": {
                "type": self.domain_id + "_result",
                "data_profile": {
                    "schema_version": "spatial-agent.data-profile.v1",
                    "primary": "metrics",
                    "kinds": ["metrics"],
                },
                "views": {
                    "schema_version": "spatial-agent.views.v1",
                    "panels": {
                        "generic": {
                            "kind": "table",
                            "title": self.domain_id,
                        }
                    },
                },
            },
        }


class _Host:
    def __init__(self, services: dict[str, _Service], *, unknown: bool = False):
        self.services = services
        self.unknown = unknown
        self.selected: list[str] = []

    def select(self, domain_id, *, source="explicit"):
        self.selected.append(domain_id)
        if self.unknown or domain_id not in self.services:
            raise DomainSelectionError("disabled", code="domain_disabled")
        return _Selection(domain_id)

    def service(self, selection):
        return self.services[selection.domain_id]


class M276CompositeCoordinatorTests(unittest.TestCase):
    def test_components_use_host_allowlist_and_execute_in_dependency_order(self):
        services = {name: _Service(name) for name in ("gis", "economic", "indicators")}
        response = CompositeApplication(host=_Host(services)).run(
            _request(), session_id="m276-session"
        )
        self.assertEqual(response["status"], "COMPLETED")
        self.assertEqual(
            [item["component_id"] for item in response["components"]],
            ["space", "economy", "independent"],
        )
        self.assertEqual(
            [item["domain_id"] for item in response["components"]],
            ["gis", "economic", "indicators"],
        )
        self.assertEqual(response["result"]["composite"]["state"], "completed")
        self.assertEqual(len(services["gis"].calls), 1)
        self.assertTrue(services["gis"].calls[0]["session_id"].startswith("composite-"))

    def test_failed_dependency_blocks_only_downstream_component(self):
        services = {
            "gis": _Service("gis", fail=True),
            "economic": _Service("economic"),
            "indicators": _Service("indicators"),
        }
        response = CompositeApplication(host=_Host(services)).run(_request())
        by_id = {item["component_id"]: item for item in response["components"]}
        self.assertEqual(response["status"], "FAILED")
        self.assertEqual(by_id["space"]["state"], "failed")
        self.assertEqual(by_id["economy"]["state"], "blocked")
        self.assertEqual(by_id["economy"]["blocked_by"], ["space"])
        self.assertEqual(by_id["independent"]["state"], "completed")
        self.assertEqual(len(services["economic"].calls), 0)
        self.assertEqual(len(services["indicators"].calls), 1)
        self.assertNotIn("private backend detail", str(response))

    def test_unknown_domain_is_rejected_before_service_execution(self):
        host = _Host({"gis": _Service("gis")}, unknown=True)
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "未知领域",
            "components": [{
                "component_id": "unknown",
                "domain_id": "not-enabled",
                "request": "执行",
            }],
        }
        with self.assertRaises(CompositeCoordinatorError) as context:
            CompositeApplication(host=host).run(request)
        self.assertEqual(context.exception.code, "domain_disabled")
        self.assertEqual(host.selected, ["not-enabled"])

    def test_real_host_allowlist_is_the_coordinator_selection_boundary(self):
        host = DomainRuntimeHost(
            service_factory=lambda domain_id: _Service(domain_id),
            enabled_domain_ids=("gis",),
        )
        try:
            request = {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": "通过 Host 执行",
                "components": [{
                    "component_id": "space",
                    "domain_id": "gis",
                    "request": "执行空间组件",
                }],
            }
            response = CompositeApplication(host=host).run(request)
        finally:
            host.close()
        self.assertEqual(response["status"], "COMPLETED")
        self.assertEqual(response["components"][0]["domain_id"], "gis")


if __name__ == "__main__":
    unittest.main()
