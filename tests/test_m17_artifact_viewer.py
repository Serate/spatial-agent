import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.artifact_viewer import render_artifact_html
from agent.service import AgentService


class M17ArtifactViewerTests(unittest.TestCase):
    def test_artifact_contains_safe_structured_step_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = AgentService(artifact_store=ArtifactStore(tmpdir)).run(
                "查询DEM栅格元数据", export_artifact=True
            )
            artifact = json.loads(Path(result["artifact_ref"]).read_text(encoding="utf-8"))

        self.assertEqual(artifact["plan"]["goal"], result["plan"]["goal"])
        self.assertEqual(artifact["steps"][0]["tool"], "get_raster_metadata")
        self.assertNotIn("args", artifact["steps"][0])

    def test_render_escapes_user_content_and_shows_trace(self):
        html = render_artifact_html(
            {
                "run_id": "run-1",
                "status": "FAILED",
                "request": "<script>alert(1)</script>",
                "plan": {"goal": "inspect"},
                "steps": [],
                "trace_summary": ["Run failed: bad input"],
                "error": "bad input",
            }
        )

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("Run failed: bad input", html)


if __name__ == "__main__":
    unittest.main()
