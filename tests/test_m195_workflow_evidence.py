"""M195: the Console workflow evidence seam stays domain neutral."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.gis.domain import GIS_DOMAIN_PACK


class M195WorkflowEvidenceTests(unittest.TestCase):
    def test_frontend_renderer_and_http_assets_are_registered(self):
        root = Path(__file__).parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        module = (root / "web" / "console_workflow_evidence.js").read_text(encoding="utf-8")
        serve_api = (root / "serve_api.py").read_text(encoding="utf-8")
        production_api = (root / "production_api.py").read_text(encoding="utf-8")

        self.assertIn('src="./console_workflow_evidence.js"', html)
        self.assertIn('id="workflowEvidenceWorkspace"', html)
        self.assertIn("renderWorkflowEvidence", html)
        self.assertIn("spatial-agent.workflow-evidence.v1", module)
        self.assertNotIn("洪山区", module)
        self.assertNotIn("get_raster_metadata", module)
        self.assertIn('"console_workflow_evidence.js"', serve_api)
        self.assertIn('"console_workflow_evidence.js"', production_api)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_node_workflow_evidence_smoke(self):
        root = Path(__file__).parents[1]
        completed = subprocess.run(
            ["node", str(root / "scripts" / "console_workflow_evidence_smoke.js")],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("console workflow evidence smoke passed", completed.stdout)

    def test_component_projection_preserves_evidence_keys(self):
        with tempfile.TemporaryDirectory(prefix="m195-workflow-evidence-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                preview = service.preview(
                    "组合查询洪山区边界和 DEM 元数据",
                    session_id="m195-evidence",
                    planner="rule",
                    backend="memory",
                    workflow={
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
                    },
                )
            finally:
                service.close()
        components = preview["plan_evidence"]["workflow_selection"]["workflow_components"]
        self.assertEqual([item["component_id"] for item in components], ["boundary", "dem"])
        self.assertTrue(all("evidence_keys" in item for item in components))
        self.assertTrue(all(item["evidence_keys"] for item in components))


if __name__ == "__main__":
    unittest.main()
