import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

from scripts.convert_osm_to_gpkg import _road_level, _water_geometry


HAS_SHAPELY = importlib.util.find_spec("shapely") is not None


@unittest.skipUnless(HAS_SHAPELY, "requires shapely in the GIS environment")
class OsmConverterTests(unittest.TestCase):
    def test_road_level_keeps_major_highway_classes(self):
        self.assertEqual(_road_level({"highway": "primary"}), "primary")
        self.assertEqual(_road_level({"highway": "residential"}), "local")

    def test_closed_natural_water_way_becomes_polygon(self):
        geometry = _water_geometry({"geometry": [
            {"lon": 0, "lat": 0}, {"lon": 1, "lat": 0},
            {"lon": 1, "lat": 1}, {"lon": 0, "lat": 0},
        ]}, {"natural": "water"})
        self.assertEqual(geometry.geom_type, "Polygon")

    def test_open_waterway_remains_line(self):
        geometry = _water_geometry({"geometry": [
            {"lon": 0, "lat": 0}, {"lon": 1, "lat": 1},
        ]}, {"waterway": "river"})
        self.assertEqual(geometry.geom_type, "LineString")


if __name__ == "__main__":
    unittest.main()
