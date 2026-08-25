import unittest

from agent.analysis.record_analysis import RecordAnalysisEngine
from agent.analysis.record_views import build_record_analysis_view


class M269RecordAnalysisTests(unittest.TestCase):
    def test_filter_returns_bounded_safe_rows(self):
        engine = RecordAnalysisEngine(dataset_id="events")
        result = engine.analyze(
            [
                {
                    "mag": 2.4,
                    "place": "西侧",
                    "geometry": {"type": "Point", "coordinates": [114.3, 30.5]},
                    "path": "D:/private/events.geojson",
                },
                {"mag": 3.1, "place": "东侧"},
            ],
            operation="filter",
            filters=[{"field": "mag", "operator": "gte", "value": 2.5}],
            limit=10,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["operation"], "filter")
        self.assertEqual(result["metrics"]["filtered_count"], 1)
        self.assertEqual(result["rows"], [{"mag": 3.1, "place": "东侧"}])
        self.assertNotIn("geometry", result["rows"])
        self.assertNotIn("path", result["rows"])

    def test_aggregate_groups_and_calculates_metrics(self):
        engine = RecordAnalysisEngine(dataset_id="events")
        result = engine.analyze(
            [
                {"place": "东侧", "mag": 2.0},
                {"place": "东侧", "mag": 3.0},
                {"place": "西侧", "mag": 4.0},
            ],
            operation="aggregate",
            group_by=["place"],
            aggregations=[
                {"field": "mag", "function": "mean", "alias": "mean_mag"},
                {"function": "count", "alias": "event_count"},
            ],
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["data_profile"]["primary"], "metrics")
        self.assertEqual(
            result["rows"],
            [
                {"event_count": 2, "mean_mag": 2.5, "place": "东侧"},
                {"event_count": 1, "mean_mag": 4, "place": "西侧"},
            ],
        )

    def test_timeseries_and_compare_share_the_same_operation_contract(self):
        records = [
            {"region": "甲", "period": "2023", "value": 10},
            {"region": "甲", "period": "2024", "value": 12},
            {"region": "乙", "period": "2024", "value": 8},
        ]
        engine = RecordAnalysisEngine(dataset_id="regional_metrics")
        trend = engine.analyze(
            records,
            operation="timeseries",
            group_by=["region"],
            time_field="period",
            aggregations=[{"field": "value", "function": "mean", "alias": "mean_value"}],
        )
        comparison = engine.analyze(
            records,
            operation="compare",
            group_by=["region"],
            aggregations=[{"field": "value", "function": "mean", "alias": "mean_value"}],
        )

        self.assertEqual(trend["data_profile"]["primary"], "timeseries")
        self.assertEqual([row["period"] for row in trend["rows"]], ["2023", "2024", "2024"])
        self.assertEqual(comparison["data_profile"]["primary"], "composite")
        by_region = {row["region"]: row for row in comparison["rows"]}
        self.assertEqual(by_region["甲"], {"mean_value": 11, "region": "甲"})

    def test_missing_field_is_structured_and_non_retryable(self):
        result = RecordAnalysisEngine(dataset_id="events").analyze(
            [{"mag": 2.5}],
            operation="aggregate",
            group_by=["unknown_field"],
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["code"], "record_field_mismatch")
        self.assertFalse(result["retryable"])
        self.assertEqual(result["missing_fields"], ["unknown_field"])

    def test_shared_view_exposes_table_and_chart_without_geometry(self):
        result = RecordAnalysisEngine(dataset_id="events").analyze(
            [
                {"region": "甲", "period": "2024", "value": 10},
                {"region": "甲", "period": "2025", "value": 12},
            ],
            operation="timeseries",
            group_by=["region"],
            time_field="period",
            aggregations=[{"field": "value", "function": "mean", "alias": "mean_value"}],
        )
        view = build_record_analysis_view(result)
        self.assertEqual(view["kind"], "comparison_chart")
        self.assertEqual(view["table"]["columns"], ["region", "period", "mean_value"])
        self.assertEqual(len(view["series"][0]["points"]), 2)
        self.assertNotIn("geometry", view)


if __name__ == "__main__":
    unittest.main()
