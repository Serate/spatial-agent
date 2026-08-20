import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class M66DataVolumeContractTests(unittest.TestCase):
    def test_container_catalog_declares_core_data_under_container_root(self):
        config = json.loads(
            (ROOT / "config" / "datasets.container.example.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(config["root"], "/data")
        self.assertEqual(
            set(config["datasets"]),
            {"admin_areas", "dem", "land_use", "roads", "water"},
        )
        self.assertTrue(config["datasets"]["admin_areas"]["path"])
        # M79.4.1: the container catalog points core rasters at the
        # analysis-ready aligned derivatives instead of the raw tiles.
        self.assertIn("dem", config["datasets"]["dem"].get("path") or config["datasets"]["dem"].get("glob") or "")
        self.assertIn("analysis-ready", config["datasets"]["dem"].get("path") or "")
        self.assertIn("analysis-ready", config["datasets"]["land_use"].get("path") or "")
        self.assertIn("wuhan-osm.gpkg", config["datasets"]["roads"].get("path") or "")
        self.assertIn("wuhan-osm.gpkg", config["datasets"]["water"].get("path") or "")

    def test_compose_separates_read_only_data_from_writable_outputs(self):
        compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        self.assertIn("${SPATIAL_AGENT_HOST_DATASET_ROOT:-./data}:/data:ro", compose)
        self.assertIn("./outputs:/app/outputs", compose)
        self.assertNotIn("/data:rw", compose)

    def test_docker_runtime_points_at_container_catalog_and_requires_gis(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("SPATIAL_AGENT_DATASET_CONFIG=/app/config/datasets.container.example.json", dockerfile)
        self.assertIn("SPATIAL_AGENT_DATASET_ROOT=/data", dockerfile)
        self.assertIn("SPATIAL_AGENT_REQUIRE_GIS=1", dockerfile)
        self.assertIn('"--workers", "2"', dockerfile)

    def test_acceptance_checks_core_and_reports_optional_dataset_gap(self):
        script = (ROOT / "scripts" / "production_acceptance.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("function Assert-DataVolumeHealth", script)
        for dataset in ("admin_areas", "dem", "land_use", "roads", "water"):
            self.assertIn(f'"{dataset}"', script)
        self.assertIn("core data volume is unavailable", script)
        self.assertIn("optional_missing_datasets", script)
        self.assertIn("core_ready_optional_partial", script)

    def test_acceptance_checks_m82_planning_evidence_and_artifact(self):
        script = (ROOT / "scripts" / "production_acceptance.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("function Assert-PlanningEvidence", script)
        self.assertIn("function Assert-DegradationEvidence", script)
        self.assertIn("function Assert-WorkspaceEvidence", script)
        self.assertIn("function Assert-ViewEvidence", script)
        self.assertIn("capability_discovery_available", script)
        self.assertIn("capability_catalog_available", script)
        self.assertIn("selected_capability_id", script)
        self.assertIn("capability_catalog_environment", script)
        self.assertIn("spatial-agent.degradation.v1", script)
        self.assertIn("spatial-agent.workspace.v1", script)
        self.assertIn("spatial-agent.views.v1", script)
        self.assertIn("sync_degradation_status", script)
        self.assertIn("sync_workspace_panels", script)
        self.assertIn("sync_view_panels", script)
        self.assertIn("$viewPanelNames", script)
        self.assertIn("IsNullOrWhiteSpace", script)
        self.assertIn("export_artifact = $true", script)
        self.assertIn("/artifacts/runs/", script)
        self.assertIn("sync_selected_capability", script)
        self.assertIn("runtime tool provider evidence missing", script)
        self.assertIn("spatial-agent.tool-provider-health.v1", script)
        self.assertIn("spatial-agent.tool-provider-contract.v1", script)
        self.assertIn("spatial-agent.tool-governance.v1", script)
        self.assertIn("runtime_tool_provider_health", script)
        self.assertIn("spatial-agent.request-facts.v1", script)
        self.assertIn("spatial-agent.execution-policy.v1", script)
        self.assertIn("function Assert-FailureEvidence", script)
        self.assertIn("spatial-agent.failure.v1", script)
        self.assertIn("artifact request facts evidence missing", script)
        self.assertIn("function Assert-ReplanningEvidence", script)
        self.assertIn("spatial-agent.replanning.v1", script)
        self.assertIn("replanning lineage count mismatch", script)
        self.assertIn("result replanning envelope missing", script)
        self.assertIn("function Assert-DeploymentEvidence", script)
        self.assertIn("spatial-agent.deployment-evidence.v1", script)
        self.assertIn("deployment context fingerprint mismatch", script)
        self.assertIn("runtime and release deployment context fingerprints differ", script)
        self.assertIn("/release-evidence?max_files=1", script)
        self.assertIn("runtime_deployment_status", script)
        self.assertIn("release_deployment_status", script)
        self.assertIn("sync_deployment_status", script)

    @unittest.skipUnless(
        os.environ.get("SPATIAL_AGENT_RUN_M66_PRODUCTION") == "1",
        "set SPATIAL_AGENT_RUN_M66_PRODUCTION=1 for a live Docker acceptance",
    )
    def test_live_production_acceptance(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "production_acceptance.ps1"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
