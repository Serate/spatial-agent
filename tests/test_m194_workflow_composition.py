"""M194-A: bounded workflow components compile into one isolated DAG."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from agent.workflow_templates import (
    WORKFLOW_COMPOSITION_SCHEMA_VERSION,
    WorkflowTemplateError,
    compile_workflow_composition,
    normalize_workflow_composition,
)
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TextDomainPack


class M194WorkflowCompositionTests(unittest.TestCase):
    def test_component_dependencies_are_normalized_and_prefixed(self):
        workflow = normalize_workflow_composition(
            {
                "components": [
                    {
                        "component_id": "boundary",
                        "template_id": "admin_boundary_query",
                        "constraints": {"admin_name": "洪山区"},
                    },
                    {
                        "component_id": "dem",
                        "template_id": "raster_metadata",
                        "constraints": {"dataset": "dem"},
                        "depends_on_components": ["boundary"],
                    },
                ]
            }
        )

        self.assertEqual(workflow["schema_version"], WORKFLOW_COMPOSITION_SCHEMA_VERSION)
        self.assertEqual(workflow["component_template_ids"], ["admin_boundary_query", "raster_metadata"])
        self.assertEqual(workflow["components"][1]["depends_on_components"], ["boundary"])

        plan = compile_workflow_composition(workflow["components"], output_type="spatial_analysis_result")
        ids = [step["id"] for step in plan["steps"]]
        self.assertEqual(len(ids), len(set(ids)))
        dem_roots = [step for step in plan["steps"] if step["id"].startswith("dem--") and not step["depends_on"]]
        self.assertEqual(dem_roots, [])
        dem_steps = [step for step in plan["steps"] if step["id"].startswith("dem--")]
        self.assertTrue(any("boundary--filter-admin" in step["depends_on"] for step in dem_steps))

    def test_gis_domain_runs_explicit_component_workflow(self):
        workflow = GIS_DOMAIN_PACK.normalize_workflow(
            {
                "components": [
                    {
                        "component_id": "boundary",
                        "template_id": "admin_boundary_query",
                        "constraints": {"admin_name": "洪山区"},
                    },
                    {
                        "component_id": "dem",
                        "template_id": "raster_metadata",
                        "constraints": {"dataset": "dem"},
                    },
                ]
            }
        )
        plan = GIS_DOMAIN_PACK.rule_planner().plan("组合查询", workflow=workflow)

        self.assertEqual(plan.output["type"], "spatial_analysis_result")
        self.assertEqual(plan.output["component_template_ids"], ["admin_boundary_query", "raster_metadata"])
        self.assertTrue(all("--" in step.id for step in plan.steps))
        GIS_DOMAIN_PACK.validate_workflow_plan(plan, workflow)

    def test_service_preview_and_run_keep_component_dag(self):
        raw_workflow = {
            "components": [
                {
                    "component_id": "boundary",
                    "template_id": "admin_boundary_query",
                    "constraints": {"admin_name": "洪山区"},
                },
                {
                    "component_id": "dem",
                    "template_id": "raster_metadata",
                    "constraints": {"dataset": "dem"},
                },
            ]
        }
        with tempfile.TemporaryDirectory(prefix="m194-composition-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                preview = service.preview(
                    "组合查询洪山区边界和 DEM 元数据",
                    session_id="m194-composition-preview",
                    planner="rule",
                    backend="memory",
                    workflow=raw_workflow,
                )
                completed = service.run(
                    "组合查询洪山区边界和 DEM 元数据",
                    session_id="m194-composition-run",
                    planner="rule",
                    backend="memory",
                    workflow=raw_workflow,
                    preview_fingerprint=preview["plan_identity"]["fingerprint"],
                    export_artifact=True,
                )
            finally:
                service.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["plan"]["output"]["type"], "spatial_analysis_result")
        self.assertEqual(
            completed["plan"]["output"]["component_template_ids"],
            ["admin_boundary_query", "raster_metadata"],
        )
        self.assertTrue(all("--" in step["id"] for step in completed["plan"]["steps"]))
        self.assertTrue(completed.get("artifact_ref"))

    def test_text_domain_does_not_import_gis_component_templates(self):
        with self.assertRaises(ValueError):
            TextDomainPack().normalize_workflow(
                {
                    "components": [
                        {"template_id": "text_summary", "constraints": {}}
                    ]
                }
            )

    def test_component_dependency_cycle_is_rejected(self):
        with self.assertRaises(WorkflowTemplateError):
            normalize_workflow_composition(
                {
                    "components": [
                        {"component_id": "a", "template_id": "raster_metadata", "constraints": {"dataset": "dem"}, "depends_on_components": ["b"]},
                        {"component_id": "b", "template_id": "raster_metadata", "constraints": {"dataset": "slope"}, "depends_on_components": ["a"]},
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
