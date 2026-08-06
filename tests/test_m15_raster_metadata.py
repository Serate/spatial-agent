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

    def test_rule_planner_runs_raster_statistics_offline(self):
        runtime = build_runtime("rule", "memory")
        result = runtime.run("分析DEM高程统计")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "raster_statistics_result")
        self.assertEqual(result.steps[0].tool, "get_raster_statistics")
        self.assertEqual(result.steps[0].result["statistics"]["mean"], 0.0)
        self.assertIn("dem 栅格统计", result.answer)

    def test_rule_planner_selects_zonal_raster_statistics(self):
        runtime = build_runtime("rule", "memory")
        result = runtime.run("分析洪山区DEM高程概况")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "zonal_raster_statistics_result")
        self.assertEqual(result.steps[0].tool, "get_zonal_raster_statistics")
        self.assertEqual(result.steps[0].args["admin_name"], "洪山区")
        self.assertIn("洪山区", result.answer)


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

    def test_computes_dem_statistics_in_streaming_blocks(self):
        result = self.build_backend().get_raster_statistics("dem", max_files=2)

        statistics = result["statistics"]
        self.assertEqual(result["dataset"], "dem")
        self.assertEqual(result["metrics"]["analyzed_files"], 2)
        self.assertGreater(statistics["valid_pixel_count"], 0)
        self.assertLessEqual(statistics["minimum"], statistics["mean"])
        self.assertLessEqual(statistics["mean"], statistics["maximum"])
        self.assertGreaterEqual(statistics["nodata_ratio"], 0.0)
        self.assertLessEqual(statistics["nodata_ratio"], 1.0)
        self.assertTrue(statistics["distribution"]["sampled"])
        self.assertGreater(len(statistics["distribution"]["bins"]), 0)

    def test_computes_zonal_dem_statistics_for_admin_area(self):
        result = build_runtime("rule", "local").run("分析洪山区DEM高程概况")

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].tool, "get_zonal_raster_statistics")
        statistics = result.steps[0].result["statistics"]
        self.assertGreater(statistics["valid_pixel_count"], 0)
        self.assertLessEqual(statistics["minimum"], statistics["mean"])
        self.assertLessEqual(statistics["mean"], statistics["maximum"])
        self.assertEqual(len(result.steps[0].result["bounds"]), 4)
        self.assertTrue(result.steps[0].result["crs"])
        self.assertIn("洪山区", result.answer)


if __name__ == "__main__":
    unittest.main()
