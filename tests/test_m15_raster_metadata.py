import importlib.util
import unittest
from pathlib import Path

from agent.dataset_catalog import DatasetCatalog
from agent.raster_backend import RasterMetadataBackend
from run_demo import build_runtime


ROOT = Path(__file__).parents[1]
HAS_RASTERIO = importlib.util.find_spec("rasterio") is not None
HAS_LOCAL_RASTER = Path("D:/dataset/agent").exists()


class M15RasterMetadataTests(unittest.TestCase):
    def test_rule_planner_runs_raster_metadata_tool_offline(self):
        runtime = build_runtime("rule", "memory")
        result = runtime.run("查询DEM栅格元数据")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "raster_metadata_result")
        self.assertEqual(result.steps[0].tool, "get_raster_metadata")
        self.assertEqual(result.steps[0].result["dataset"], "dem")
        self.assertEqual(result.steps[0].result["metrics"]["backend"], "in_memory")
        self.assertIn("dem 栅格元数据", result.answer)

    def test_rule_planner_selects_land_use_metadata(self):
        runtime = build_runtime("rule", "memory")
        result = runtime.run("查询土地利用栅格元数据")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].result["dataset"], "land_use")


@unittest.skipUnless(HAS_RASTERIO and HAS_LOCAL_RASTER, "requires rasterio and local raster dataset files")
class M15LocalRasterMetadataTests(unittest.TestCase):
    def build_backend(self):
        catalog = DatasetCatalog.from_json(str(ROOT / "config" / "datasets.local.example.json"))
        return RasterMetadataBackend(catalog)

    def test_reads_dem_raster_metadata_without_array_processing(self):
        result = self.build_backend().get_raster_metadata("dem", max_files=2)

        self.assertEqual(result["dataset"], "dem")
        self.assertGreater(result["file_count"], 0)
        self.assertEqual(result["metrics"]["probed_files"], 2)
        self.assertGreater(result["metadata"]["width"], 0)
        self.assertGreater(result["metadata"]["height"], 0)
        self.assertGreater(result["metadata"]["band_count"], 0)
        self.assertTrue(result["metadata"]["crs_values"])
        self.assertTrue(result["metadata"]["bounds"])

    def test_reads_land_use_raster_metadata(self):
        result = self.build_backend().get_raster_metadata("land_use", max_files=2)

        self.assertEqual(result["dataset"], "land_use")
        self.assertGreater(result["file_count"], 0)
        self.assertEqual(result["metrics"]["probed_files"], 2)
        self.assertGreater(result["metadata"]["width"], 0)
        self.assertGreater(result["metadata"]["height"], 0)


if __name__ == "__main__":
    unittest.main()
