"""M122 domain-owned views and generic Console smoke contracts."""

import unittest
from pathlib import Path

from domains.text.runtime import build_text_runtime
from result_contract import build_result_contract


ROOT = Path(__file__).parents[1]


class M122DomainViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
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

    def test_text_result_uses_only_generic_workspace_in_console(self):
        runtime = build_text_runtime()
        result = runtime.run("请摘要这段文本。")
        payload = build_result_contract(
            {**result.to_dict(), "result_type": result.plan.output["type"]},
            registry=runtime.result_registry(),
        )

        self.assertEqual(payload["type"], "text_summary_result")
        self.assertEqual(payload["workspace"]["panels"], ["generic"])
        self.assertEqual(payload["views"]["panels"], {})
        self.assertIn("workspacePanelSelectors", self.html)
        self.assertIn("generic: '.generic-result'", self.html)
        self.assertIn("const views=new Set(Array.isArray(workspace.panels)?workspace.panels:[])", self.html)
        self.assertIn("views.has('generic')", self.html)
        self.assertNotIn("text_summary_result", self.html)
        self.assertNotIn("outputType==='text_summary_result'", self.html)


if __name__ == "__main__":
    unittest.main()
