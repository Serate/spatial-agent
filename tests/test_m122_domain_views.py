"""M122 domain-owned views and generic Console smoke contracts."""

import unittest
from pathlib import Path

from tests.console_source import read_console_source

from domains.text.runtime import build_text_runtime
from agent.result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec
from result_contract import build_result_contract


ROOT = Path(__file__).parents[1]


class M122DomainViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read_console_source(ROOT)
        cls.result_contract_source = (ROOT / "result_contract.py").read_text(encoding="utf-8")

    def test_gis_view_builder_is_owned_by_gis_domain(self):
        from domains.gis.result_registry import GIS_RESULT_REGISTRY
        from domains.gis.views import build_views

        self.assertIs(GIS_RESULT_REGISTRY._view_builder, build_views)
        self.assertNotIn("def _view_model", self.result_contract_source)
        self.assertNotIn("from result_contract import _view_model", self.result_contract_source)

        result = build_result_contract(
            {
                "result_type": "raster_metadata_result",
                "status": "COMPLETED",
                "steps": [
                    {
                        "id": "metadata",
                        "tool": "get_raster_metadata",
                        "status": "COMPLETED",
                        "result": {
                            "dataset": "dem",
                            "file_count": 1,
                            "metadata": {"width": 4, "height": 5, "band_count": 1},
                        },
                    }
                ],
            }
        )
        self.assertEqual(result["views"]["panels"]["raster"]["kind"], "raster_metadata")
        self.assertEqual(result["workspace"]["view_specs"][0]["id"], "raster")
        self.assertEqual(result["workspace"]["view_specs"][0]["renderer"], "metrics")

    def test_text_result_uses_only_generic_workspace_in_console(self):
        runtime = build_text_runtime()
        result = runtime.run("请摘要这段文本。")
        payload = build_result_contract(
            {**result.to_dict(), "result_type": result.plan.output["type"]},
            registry=runtime.result_registry(),
        )

        self.assertEqual(payload["type"], "text_summary_result")
        self.assertEqual(payload["data_profile"]["primary"], "text")
        self.assertIn("document_evidence", payload["data_profile"]["kinds"])
        self.assertEqual(payload["workspace"]["panels"], ["generic"])
        self.assertEqual(payload["views"]["panels"]["generic"]["kind"], "text_summary")
        self.assertEqual(payload["workspace"]["view_specs"][0]["id"], "generic")
        self.assertEqual(payload["workspace"]["view_specs"][0]["renderer"], "generic")
        self.assertIn("rendererRegistry.renderWorkspace", self.html)
        self.assertIn("setResultPanel('.generic-result',visible)", self.html)
        self.assertIn("resultViewPanels(data)", self.html)
        self.assertIn("compositeViewProjection(data)", self.html)
        self.assertIn("$('genericResult')", self.html)
        self.assertNotIn("text_summary_result", self.html)
        self.assertNotIn("outputType==='text_summary_result'", self.html)
        self.assertNotIn("const needsRaster=", self.html)

    def test_non_gis_domain_can_declare_a_generic_renderer_view(self):
        registry = ResultContractRegistry(
            {
                "custom_result": ResultTypeSpec(
                    title="自定义结果",
                    panels=("insights",),
                    view_specs=(ViewSpec("insights", "metrics", "指标"),),
                )
            },
            view_builder=lambda *args, **kwargs: {
                "schema_version": "spatial-agent.views.v1",
                "panels": {
                    "insights": {
                        "kind": "summary",
                        "metrics": [{"label": "项目数", "value": 2}],
                    }
                },
            },
        )
        result = build_result_contract(
            {
                "result_type": "custom_result",
                "status": "COMPLETED",
                "answer": "已完成",
                "steps": [],
            },
            registry=registry,
        )

        self.assertEqual(result["workspace"]["panels"], ["insights"])
        self.assertEqual(
            result["workspace"]["view_specs"],
            [
                {
                    "id": "insights",
                    "renderer": "metrics",
                    "title": "指标",
                    "schema_version": "spatial-agent.view.v1",
                }
            ],
        )

    def test_failed_generic_view_keeps_degradation_and_artifact_state(self):
        runtime = build_text_runtime()
        payload = build_result_contract(
            {
                "result_type": "text_summary_result",
                "status": "FAILED",
                "error": "摘要工具失败",
                "artifact_ref": "outputs/runs/example.json",
                "steps": [],
            },
            registry=runtime.result_registry(),
        )

        view = payload["views"]["panels"]["generic"]
        self.assertEqual(view["kind"], "unavailable")
        self.assertTrue(view["artifact_available"])
        self.assertIn("失败", view["reason"])
        self.assertIn("projectionToPanels", self.html)
        self.assertIn("data.artifact_ref", self.html)


if __name__ == "__main__":
    unittest.main()
