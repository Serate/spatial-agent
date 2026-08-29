import math
import unittest

from domains.gis.adapters.raster_alignment import (
    ALIGNMENT_STATUSES,
    compare_raster_alignment,
    raster_alignment_report,
)


def metadata(**overrides):
    value = {
        "crs": "EPSG:32649",
        "bounds": [100.0, 200.0, 140.0, 240.0],
        "width": 4,
        "height": 4,
        "pixel_size": [10.0, 10.0],
        "transform": [10.0, 0.0, 100.0, 0.0, -10.0, 240.0],
    }
    value.update(overrides)
    return value


class M68RasterAlignmentTests(unittest.TestCase):
    def test_aligned_report_is_metadata_only_and_strictly_comparable(self):
        report = raster_alignment_report(metadata(pixels="must not be read"), metadata())

        self.assertEqual(report["status"], "aligned")
        self.assertTrue(report["aligned"])
        self.assertTrue(report["comparable"])
        self.assertTrue(report["evidence"]["metadata_only"])
        self.assertFalse(report["evidence"]["pixels_read"])
        self.assertEqual(report["comparison"]["bounds"]["overlap_area"], 1600.0)
        self.assertTrue(report["comparison"]["grid"]["dimensions_match"])

    def test_existing_raster_tool_metadata_wrapper_and_crs_values_are_supported(self):
        dem = {"dataset": "dem", "metadata": metadata(crs=None, crs_values=["epsg:32649"])}
        land_use = {"dataset": "land_use", "metadata": metadata(crs="epsg:32649")}

        report = compare_raster_alignment(dem, land_use)

        self.assertEqual(report["status"], "aligned")
        self.assertEqual(report["dem"]["crs"], "EPSG:32649")

    def test_bounds_mapping_is_a_controlled_metadata_shape(self):
        bounds = {"left": 100.0, "bottom": 200.0, "right": 140.0, "top": 240.0}
        report = raster_alignment_report(metadata(bounds=bounds), metadata())

        self.assertEqual(report["status"], "aligned")
        self.assertEqual(report["dem"]["bounds"], [100.0, 200.0, 140.0, 240.0])

    def test_all_public_statuses_are_declared(self):
        self.assertEqual(
            set(ALIGNMENT_STATUSES),
            {"missing_metadata", "crs_mismatch", "no_overlap", "resolution_mismatch", "grid_mismatch", "aligned"},
        )

    def test_missing_metadata_is_explicit_for_each_input(self):
        report = raster_alignment_report({"crs": "EPSG:4326"}, metadata())

        self.assertEqual(report["status"], "missing_metadata")
        self.assertFalse(report["aligned"])
        self.assertEqual(
            set(report["missing_fields"]["dem"]),
            {"bounds", "width", "height", "pixel_size"},
        )
        self.assertEqual(report["missing_fields"]["land_use"], [])

    def test_crs_mismatch_is_reported_before_spatial_comparison(self):
        report = raster_alignment_report(metadata(crs="EPSG:4326"), metadata())

        self.assertEqual(report["status"], "crs_mismatch")
        self.assertFalse(report["comparison"]["crs"]["match"])
        self.assertEqual(report["comparison"]["crs"]["dem"], "EPSG:4326")

    def test_touching_or_disjoint_bounds_are_no_overlap(self):
        touching = raster_alignment_report(
            metadata(bounds=[140.0, 200.0, 180.0, 240.0], transform=None),
            metadata(),
        )
        disjoint = raster_alignment_report(
            metadata(bounds=[0.0, 0.0, 40.0, 40.0], transform=None),
            metadata(),
        )

        self.assertEqual(touching["status"], "no_overlap")
        self.assertEqual(disjoint["status"], "no_overlap")
        self.assertFalse(touching["comparison"]["bounds"]["overlap"])
        self.assertIsNone(disjoint["comparison"]["bounds"]["intersection"])

    def test_resolution_mismatch_is_distinguished_from_grid_mismatch(self):
        report = raster_alignment_report(
            metadata(
                bounds=[100.0, 200.0, 180.0, 280.0],
                pixel_size=[20.0, 20.0],
                transform=[20.0, 0.0, 100.0, 0.0, -20.0, 280.0],
            ),
            metadata(),
        )

        self.assertEqual(report["status"], "resolution_mismatch")
        self.assertFalse(report["comparison"]["resolution"]["match"])

    def test_same_resolution_with_different_origin_is_grid_mismatch(self):
        shifted = metadata(
            bounds=[101.0, 200.0, 141.0, 240.0],
            transform=[10.0, 0.0, 101.0, 0.0, -10.0, 240.0],
        )
        report = raster_alignment_report(metadata(), shifted)

        self.assertEqual(report["status"], "grid_mismatch")
        self.assertTrue(report["comparison"]["bounds"]["overlap"])
        self.assertFalse(report["comparison"]["grid"]["origin_phase_match"])

    def test_same_origin_but_different_extent_or_dimensions_is_grid_mismatch(self):
        report = raster_alignment_report(
            metadata(bounds=[100.0, 200.0, 150.0, 240.0], width=5),
            metadata(),
        )

        self.assertEqual(report["status"], "grid_mismatch")
        self.assertTrue(report["comparison"]["grid"]["origin_phase_match"])
        self.assertFalse(report["comparison"]["grid"]["extent_match"])
        self.assertFalse(report["comparison"]["grid"]["dimensions_match"])

    def test_transform_can_supply_pixel_size_and_origin(self):
        base = metadata(pixel_size=None)
        report = raster_alignment_report(base, metadata())

        self.assertEqual(report["status"], "aligned")
        self.assertEqual(report["dem"]["pixel_size"], [10.0, 10.0])
        self.assertEqual(report["dem"]["origin"], [100.0, 240.0])

    def test_transform_and_pixel_size_conflict_is_invalid_metadata(self):
        report = raster_alignment_report(
            metadata(transform=[20.0, 0.0, 100.0, 0.0, -20.0, 240.0]),
            metadata(),
        )

        self.assertEqual(report["status"], "missing_metadata")
        self.assertTrue(any("pixel_size" in item for item in report["validation_errors"]["dem"]))

    def test_rotated_transform_is_not_claimed_aligned(self):
        report = raster_alignment_report(
            metadata(transform=[10.0, 1.0, 100.0, 0.0, -10.0, 240.0]),
            metadata(),
        )

        self.assertEqual(report["status"], "grid_mismatch")
        self.assertTrue(report["comparison"]["grid"]["rotated"])

    def test_input_boundaries_return_controlled_missing_metadata_report(self):
        cases = [
            None,
            [],
            {"crs": "EPSG:4326", "bounds": [0, 0, 0, 1], "width": 1, "height": 1, "pixel_size": [1, 1]},
            metadata(width=0),
            metadata(height=True),
            metadata(pixel_size=[0, 10]),
            metadata(bounds=[0, 1, 2]),
            metadata(transform=[1, 0, 0]),
        ]

        for invalid in cases:
            with self.subTest(invalid=invalid):
                report = raster_alignment_report(invalid, metadata())
                self.assertEqual(report["status"], "missing_metadata")
                self.assertFalse(report["aligned"])
                self.assertTrue(report["evidence"]["metadata_only"])

    def test_inconsistent_dimensions_are_rejected_without_reading_pixels(self):
        report = raster_alignment_report(metadata(width=5, pixels=[1, 2, 3]), metadata())

        self.assertEqual(report["status"], "missing_metadata")
        self.assertIn("bounds width", " ".join(report["validation_errors"]["dem"]))
        self.assertFalse(report["evidence"]["pixels_read"])

    def test_transform_extent_must_agree_with_bounds(self):
        report = raster_alignment_report(
            metadata(transform=[10.0, 0.0, 101.0, 0.0, -10.0, 240.0]),
            metadata(),
        )

        self.assertEqual(report["status"], "missing_metadata")
        self.assertIn("bounds do not agree", " ".join(report["validation_errors"]["dem"]))

    def test_tolerance_controls_float_comparison_but_rejects_invalid_values(self):
        near = metadata(pixel_size=[10.0 + 1e-10, 10.0], transform=None)
        report = raster_alignment_report(metadata(), near, tolerance=1e-8)

        self.assertEqual(report["status"], "aligned")
        with self.assertRaises(ValueError):
            raster_alignment_report(metadata(), metadata(), tolerance=-1)
        with self.assertRaises(ValueError):
            raster_alignment_report(metadata(), metadata(), tolerance=math.inf)


if __name__ == "__main__":
    unittest.main()
