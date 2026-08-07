import unittest

from agent.service import AgentService


class M47SpatialContextTests(unittest.TestCase):
    def test_map_context_resolves_an_area_without_repeating_its_name(self):
        payload = AgentService().run(
            "分析当前区域地形",
            backend="memory",
            spatial_context={
                "admin_name": "洪山区",
                "source": "geojson",
                "crs": "EPSG:4490",
                "geometry_type": "MultiPolygon",
                "geometry_available": True,
            },
        )

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertIn("洪山区", payload["resolved_request"])
        self.assertEqual(payload["spatial_context"]["admin_name"], "洪山区")
        self.assertEqual(payload["result_type"], "zonal_raster_statistics_result")

    def test_spatial_context_is_bounded_and_rejects_non_objects(self):
        service = AgentService()
        with self.assertRaises(ValueError):
            service.run("你好", spatial_context="洪山区")

        payload = service.run(
            "你好",
            spatial_context={"admin_name": "洪山区", "unknown": "ignored", "geometry_available": True},
        )
        self.assertEqual(payload["spatial_context"], {"admin_name": "洪山区", "geometry_available": True})


if __name__ == "__main__":
    unittest.main()
