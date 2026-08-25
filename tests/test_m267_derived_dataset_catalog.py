"""Compact contract tests for derived datasets in a Domain catalog."""

from __future__ import annotations

import unittest

from agent.capability_catalog import capability_context_summary
from agent.domain_catalog import build_domain_catalog, validate_domain_catalog_spec
from domains.gis.catalog import GIS_CAPABILITIES
from domains.gis.domain import GIS_CATALOG_SPEC, GisDomainPack


class M267DerivedDatasetCatalogTests(unittest.TestCase):
    def test_gis_catalog_uses_shared_builder_and_declares_slope_as_derived(self):
        validate_domain_catalog_spec(GIS_CATALOG_SPEC)
        catalog = build_domain_catalog(GIS_CATALOG_SPEC, environment="unknown")
        self.assertEqual(catalog["derived_datasets"], ["slope"])
        self.assertEqual(len(catalog["capabilities"]), len(GIS_CAPABILITIES))
        legacy = next(item for item in catalog["capabilities"] if item["id"] == "legacy_road_slope")
        self.assertEqual(legacy["derived_datasets"], ["slope"])
        self.assertNotIn("slope", catalog["dataset_groups"]["core"])

    def test_gis_pack_keeps_workflow_and_domain_surfaces(self):
        pack = GisDomainPack()
        catalog = pack.capability_catalog(environment="unknown")
        self.assertEqual(catalog["domain_id"], "gis")
        self.assertEqual(
            set(pack.workflow_template_catalog()),
            set(GIS_CATALOG_SPEC.workflow_templates),
        )

    def test_derived_dataset_is_visible_as_dependency_not_readiness(self):
        catalog = build_domain_catalog(GIS_CATALOG_SPEC, environment="unknown")
        context = capability_context_summary(
            catalog=catalog,
            selected_capability_ids=["legacy_road_slope"],
            max_capabilities=1,
        )
        capability = context["capabilities"][0]
        self.assertEqual(capability["derived_datasets"], ["slope"])
        self.assertEqual(capability["dataset_evidence"], {})


if __name__ == "__main__":
    unittest.main()
