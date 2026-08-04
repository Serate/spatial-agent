import importlib.util
import unittest
from pathlib import Path

from run_demo import build_runtime


HAS_GIS = importlib.util.find_spec("geopandas") is not None
HAS_LOCAL_DATA = Path("D:/dataset/agent/\u6e56\u5317\u7701_\u53bf.geojson").exists()
ADMIN_QUERY = "\u67e5\u8be2\u6d2a\u5c71\u533a\u884c\u653f\u533a\u8fb9\u754c"
ROAD_SLOPE_QUERY = "\u67e5\u8be2\u8ddd\u79bb\u4e3b\u5e72\u9053500\u7c73\u4ee5\u5185\u3001\u5761\u5ea6\u8d85\u8fc725\u5ea6\u7684\u533a\u57df\u3002"


class M8AnswerComposerTests(unittest.TestCase):
    def test_default_answer_keeps_result_ref_and_count(self):
        result = build_runtime("rule").run(ROAD_SLOPE_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertIn("memory://join/roads-slope", result.answer)
        self.assertIn("\u5df2\u5b8c\u6210", result.answer)
        self.assertIn("\u547d\u4e2d\u6570\u91cf", result.answer)

    def test_admin_answer_is_user_facing(self):
        result = build_runtime("rule").run(ADMIN_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertIn("\u5df2\u627e\u5230", result.answer)
        self.assertIn("1", result.answer)
        self.assertIn("memory://range/admin_areas", result.answer)


@unittest.skipUnless(HAS_GIS and HAS_LOCAL_DATA, "requires geopandas and local admin GeoJSON")
class M8AnswerComposerLocalBackendTests(unittest.TestCase):
    def test_admin_answer_mentions_real_dataset_context(self):
        result = build_runtime("rule", "local").run(ADMIN_QUERY)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertIn("\u6d2a\u5c71\u533a", result.answer)
        self.assertIn("EPSG:4490", result.answer)
        self.assertIn("geojson://range/admin_areas", result.answer)


if __name__ == "__main__":
    unittest.main()
