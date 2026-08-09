import json
import tempfile
import unittest
from pathlib import Path

from scripts.download_wuhan_osm import boundary_bbox, build_query, iter_tiles, merge_tile_files


class WuhanOsmDownloaderTests(unittest.TestCase):
    def test_iter_tiles_covers_bbox_without_exceeding_edges(self):
        tiles = list(iter_tiles([0, 0, 0.25, 0.21], 0.1))
        self.assertEqual(len(tiles), 9)
        self.assertEqual(tiles[-1][2], [0.2, 0.2, 0.25, 0.21])

    def test_iter_tiles_does_not_create_zero_width_float_edge_tile(self):
        tiles = list(iter_tiles([0.998077, 0.271928, 1.098077, 0.362866], 0.05))
        self.assertEqual(len(tiles), 4)
        self.assertTrue(all(tile[2][0] < tile[2][2] and tile[2][1] < tile[2][3] for tile in tiles))

    def test_query_uses_overpass_bbox_and_expected_layers(self):
        query = build_query([114.3, 30.5, 114.4, 30.6])
        self.assertIn("way[highway](30.5000000,114.3000000,30.6000000,114.4000000)", query)
        self.assertIn("way[natural=water]", query)
        self.assertIn("way[waterway]", query)
        self.assertIn("out geom", query)

    def test_boundary_bbox_selects_only_requested_features(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "areas.json"
            path.write_text(json.dumps({"features": [
                {"properties": {"name": "洪山区"}, "geometry": {"coordinates": [[[114, 30], [115, 31]]] }},
                {"properties": {"name": "其他区"}, "geometry": {"coordinates": [[[0, 0], [100, 100]]] }},
            ]}), encoding="utf-8")
            self.assertEqual(boundary_bbox(path, ["洪山区"]), [114.0, 30.0, 115.0, 31.0])

    def test_merge_deduplicates_osm_elements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = {"elements": [{"type": "way", "id": 2}, {"type": "way", "id": 1}]}
            (root / "a.json").write_text(json.dumps(payload), encoding="utf-8")
            (root / "b.json").write_text(json.dumps({"elements": [{"type": "way", "id": 1}, {"type": "node", "id": 3}]}), encoding="utf-8")
            result = merge_tile_files([root / "a.json", root / "b.json"])
            self.assertEqual([(item["type"], item["id"]) for item in result], [("node", 3), ("way", 1), ("way", 2)])


if __name__ == "__main__":
    unittest.main()
