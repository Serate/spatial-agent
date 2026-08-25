import unittest

from agent.analysis.indicator_core import IndicatorAnalysisConfig, IndicatorAnalysisEngine
from domains.economic.provider import EconomicToolProvider
from domains.indicators.provider import IndicatorToolProvider


class M264IndicatorCoreTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {
                "indicator": "population",
                "label": "人口",
                "region": "区域甲",
                "geography_level": "district",
                "period_type": "annual",
                "period": "2024",
                "value": 120.0,
                "unit": "万人",
                "source": {"url": "https://example.test/source", "version": "v1", "locator": "表1"},
            },
            {
                "indicator": "population",
                "label": "人口",
                "region": "区域甲",
                "geography_level": "district",
                "period_type": "annual",
                "period": "2023",
                "value": 110.0,
                "unit": "万人",
                "source": {"url": "https://example.test/source", "version": "v1", "locator": "表1"},
            },
            {
                "indicator": "population",
                "label": "人口",
                "region": "区域乙",
                "geography_level": "district",
                "period_type": "annual",
                "period": "2024",
                "value": 90.0,
                "unit": "万人",
                "source": {"url": "https://example.test/source", "version": "v1", "locator": "表1"},
            },
        ]
        self.engine = IndicatorAnalysisEngine(
            self.records,
            dataset_id="regional_metrics",
            provenance={"source": "fixture"},
            config=IndicatorAnalysisConfig(
                result_prefix="indicator",
                include_source_evidence=True,
            ),
        )

    def test_latest_trend_compare_share_period_and_statistics(self):
        trend = self.engine.query(
            {"operation": "trend", "indicator": "population", "regions": ["区域甲", "区域乙"]}
        )
        self.assertEqual(trend["data_profile"]["primary"], "timeseries")
        self.assertEqual(sorted(row["period"] for row in trend["rows"]), ["2023", "2024", "2024"])
        self.assertEqual(trend["metrics"]["changes"], {"区域甲": 10.0})

        comparison = self.engine.query(
            {"operation": "compare", "indicator": "population", "regions": ["区域甲", "区域乙"]}
        )
        self.assertEqual(comparison["data_profile"]["primary"], "composite")
        self.assertEqual(comparison["metrics"]["region_count"], 2)
        self.assertEqual(sorted(row["value"] for row in comparison["rows"]), [90.0, 120.0])

    def test_catalog_and_source_evidence_are_bounded_and_deduplicated(self):
        catalog = self.engine.list_indicators()
        self.assertEqual(catalog["indicators"][0]["periods"], ["2023", "2024"])
        self.assertEqual(catalog["indicators"][0]["geography_levels"], ["district"])

        evidence = self.engine.source_evidence(
            {"indicator": "population", "regions": ["区域甲", "区域乙"]}
        )
        self.assertEqual(evidence["data_profile"]["primary"], "document_evidence")
        self.assertEqual(len(evidence["sources"]), 1)

    def test_unavailable_state_is_structured(self):
        empty = IndicatorAnalysisEngine([], dataset_id="empty")
        result = empty.query({"operation": "latest", "indicator": "x", "regions": ["区域甲"]})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["code"], "indicator_data_unavailable")
        self.assertEqual(result["data_profile"]["primary"], "metrics")

    def test_both_domain_adapters_use_the_same_core_engine(self):
        self.assertIsInstance(IndicatorToolProvider()._engine, IndicatorAnalysisEngine)
        self.assertIsInstance(EconomicToolProvider(data_path="__missing_m264_data__.json")._engine, IndicatorAnalysisEngine)


if __name__ == "__main__":
    unittest.main()
