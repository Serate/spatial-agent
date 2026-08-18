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

    def test_render_uses_result_views_for_panel_payloads(self):
        html = render_artifact_html(
            {
                "run_id": "run-views",
                "status": "COMPLETED",
                "request": "查询DEM栅格元数据",
                "plan": {"goal": "inspect raster metadata"},
                "result": {
                    "views": {
                        "schema_version": "spatial-agent.views.v1",
                        "panels": {
                            "raster": {
                                "kind": "raster_metadata",
                                "title": "dem · 元数据",
                                "metrics": [
                                    {"label": "文件数", "value": 2},
                                    {"label": "CRS", "value": "EPSG:4326"},
                                ],
                                "note": "样本：dem.tif",
                            }
                        },
                    }
                },
                "steps": [],
                "trace_summary": [],
            }
        )

        self.assertIn("Result Views", html)
        self.assertIn("spatial-agent.views.v1", html)
        self.assertIn("raster", html)
        self.assertIn("raster_metadata", html)
        self.assertIn("文件数", html)
        self.assertIn("EPSG:4326", html)

    def test_render_uses_view_rows_and_table_payloads(self):
        html = render_artifact_html(
            {
                "run_id": "run-vector-table",
                "status": "COMPLETED",
                "request": "统计道路类型",
                "plan": {"goal": "summarize vector data"},
                "result": {
                    "views": {
                        "schema_version": "spatial-agent.views.v1",
                        "panels": {
                            "vector": {
                                "kind": "zonal_vector_summary",
                                "title": "区域矢量摘要",
                                "metrics": [{"label": "相交要素", "value": 12}],
                                "rows": [
                                    {"label": "数据集", "value": "roads"},
                                    {"label": "行政区", "value": "洪山区"},
                                ],
                                "table": {
                                    "columns": ["类别", "数量"],
                                    "rows": [["primary", 7], ["<water>", 5]],
                                },
                            }
                        },
                    }
                },
                "steps": [],
                "trace_summary": [],
            }
        )

        self.assertIn("数据集", html)
        self.assertIn("roads", html)
        self.assertIn("类别", html)
        self.assertIn("primary", html)
        self.assertNotIn("<water>", html)
        self.assertIn("&lt;water&gt;", html)

    def test_render_uses_view_chart_payloads(self):
        html = render_artifact_html(
            {
                "run_id": "run-chart",
                "status": "COMPLETED",
                "request": "对比建设候选",
                "plan": {"goal": "compare buildability"},
                "result": {
                    "views": {
                        "schema_version": "spatial-agent.views.v1",
                        "panels": {
                            "chart": {
                                "kind": "comparison_chart",
                                "title": "建设适宜性阈值对比",
                                "metrics": [{"label": "场景数", "value": 2}],
                                "series": [
                                    {
                                        "name": "候选像元",
                                        "points": [
                                            {"label": "10°", "y": 100},
                                            {"label": "20°", "y": 150},
                                        ],
                                    }
                                ],
                                "table": {"columns": ["坡度", "候选像元"], "rows": [[10, 100], [20, 150]]},
                            }
                        },
                    }
                },
                "steps": [],
                "trace_summary": [],
            }
        )

        self.assertIn("comparison_chart", html)
        self.assertIn("chart-row", html)
        self.assertIn("10°", html)
        self.assertIn("150", html)
        self.assertIn("候选像元", html)


if __name__ == "__main__":
    unittest.main()
