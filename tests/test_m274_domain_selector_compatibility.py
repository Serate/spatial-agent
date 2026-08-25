import unittest

from agent.domain_selector import CatalogDomainSelector, build_domain_discovery_snapshot
from agent.domain_selector_provider import build_domain_selector_provider
from agent.domain_registry import domain_registry


class _FakeStructuredClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete_json(self, messages, schema, *, schema_name=None):
        self.calls.append({"messages": messages, "schema": schema, "schema_name": schema_name})
        return self.result


class M274DomainSelectorCompatibilityTests(unittest.TestCase):
    def test_model_adapter_uses_provider_compatible_json_object_mode(self):
        client = _FakeStructuredClient(
            {"status": "selected", "domain_id": "economic", "capability_ids": ["economic_indicator_trend"]}
        )
        provider = build_domain_selector_provider(mode="model", client=client)
        snapshot = build_domain_discovery_snapshot(registry=domain_registry(), environment="memory")

        decision = provider.select("查询 GDP 趋势", snapshot)

        self.assertEqual(decision.selection.domain_id, "economic")
        self.assertEqual(client.calls[0]["schema_name"], None)
        self.assertEqual(client.calls[0]["schema"]["required"], ["status", "domain_id", "capability_ids", "candidates"])

    def test_catalog_fallback_uses_economic_indicator_aliases(self):
        snapshot = build_domain_discovery_snapshot(registry=domain_registry(), environment="memory")
        decision = CatalogDomainSelector().select(
            "查询洪山区 gdp_total 2022至2025年度经济趋势",
            snapshot,
        )

        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.selection.domain_id, "economic")


if __name__ == "__main__":
    unittest.main()
