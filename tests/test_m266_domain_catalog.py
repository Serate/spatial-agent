"""Compact contract tests for the declarative Domain catalog seam."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from agent.domain_catalog import (
    build_domain_catalog,
    validate_domain_catalog_spec,
    workflow_catalog,
)
from domains.economic.domain import ECONOMIC_CATALOG_SPEC, EconomicDomainPack
from domains.indicators.domain import INDICATOR_CATALOG_SPEC, IndicatorsDomainPack


class M266DomainCatalogTests(unittest.TestCase):
    def test_indicators_and_economic_share_the_builder(self):
        for spec, domain_id in (
            (INDICATOR_CATALOG_SPEC, "indicators"),
            (ECONOMIC_CATALOG_SPEC, "economic"),
        ):
            catalog = build_domain_catalog(spec, environment="memory")
            self.assertEqual(catalog["domain_id"], domain_id)
            self.assertEqual(
                catalog["declaration_schema_version"],
                "spatial-agent.domain-catalog-spec.v1",
            )
            self.assertTrue(catalog["capabilities"])
            self.assertTrue(catalog["workflow_templates"])

    def test_domain_pack_surfaces_use_the_declaration(self):
        self.assertEqual(
            IndicatorsDomainPack().capability_catalog(environment="memory")["domain_id"],
            "indicators",
        )
        self.assertEqual(
            EconomicDomainPack().capability_catalog(environment="local")["domain_id"],
            "economic",
        )

    def test_unknown_tool_reference_is_rejected_before_catalog_build(self):
        invalid = replace(
            INDICATOR_CATALOG_SPEC,
            known_tool_names=("indicator_query",),
        )
        with self.assertRaisesRegex(ValueError, "unknown tools"):
            validate_domain_catalog_spec(invalid)

    def test_workflow_tool_and_result_references_are_checked(self):
        workflows = deepcopy(ECONOMIC_CATALOG_SPEC.workflow_templates)
        workflows["economic_latest"]["allowed_tools"] = ["missing_tool"]
        invalid = replace(ECONOMIC_CATALOG_SPEC, workflow_templates=workflows)
        with self.assertRaisesRegex(ValueError, "unknown tools"):
            validate_domain_catalog_spec(invalid)

    def test_workflow_and_catalog_results_are_detached(self):
        workflows = workflow_catalog(INDICATOR_CATALOG_SPEC)
        workflows["indicator_latest"]["label"] = "changed"
        catalog = build_domain_catalog(INDICATOR_CATALOG_SPEC, environment="memory")
        self.assertNotEqual(catalog["workflow_templates"]["indicator_latest"]["label"], "changed")


if __name__ == "__main__":
    unittest.main()
