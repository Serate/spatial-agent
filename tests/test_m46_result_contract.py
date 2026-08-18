import unittest
from pathlib import Path

from agent.service import AgentService
from evaluation.runner import run_cases
from run_demo import build_runtime


class M46ResultContractTests(unittest.TestCase):
    def test_console_consumes_result_envelope_before_legacy_fields(self):
        html = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("const envelope = data.result || {}", html)
        self.assertIn("const workspace=envelope.workspace||{}", html)
        self.assertIn("const payload = data.result ||", html)

    def test_completed_run_returns_bounded_evidence_result_envelope(self):
        payload = AgentService().run("查询DEM栅格元数据", backend="memory")

        result = payload["result"]
        self.assertEqual(result["type"], "raster_metadata_result")
        self.assertEqual(result["title"], "栅格元数据")
        self.assertEqual(result["workspace"]["schema_version"], "spatial-agent.workspace.v1")
        self.assertTrue(result["workspace"]["registered_type"])
        self.assertIn("raster", result["workspace"]["panels"])
        self.assertIn("evidence", result["workspace"]["common_panels"])
        self.assertEqual(result["views"]["schema_version"], "spatial-agent.views.v1")
        raster_view = result["views"]["panels"]["raster"]
        self.assertEqual(raster_view["kind"], "raster_metadata")
        self.assertEqual(raster_view["source_step_id"], "raster-metadata")
        self.assertIn("文件数", [item["label"] for item in raster_view["metrics"]])
        self.assertIn("文件数", result["summary"])
        self.assertEqual(result["data"]["evidence_steps"][0]["tool"], "get_raster_metadata")
        self.assertNotIn("metadata", result["data"]["evidence_steps"][0]["summary"])

    def test_workspace_contract_marks_map_as_backend_decided_panel(self):
        from result_contract import build_result_contract

        result = build_result_contract({
            "run_id": "workspace-map",
            "status": "COMPLETED",
            "result_type": "raster_statistics_result",
            "answer": "已完成",
            "steps": [
                {
                    "id": "raster",
                    "tool": "get_raster_statistics",
                    "status": "COMPLETED",
                    "result": {
                        "dataset": "dem",
                        "bounds": [114.0, 30.0, 115.0, 31.0],
                        "statistics": {"mean": 10},
                    },
                }
            ],
        })

        self.assertIn("raster", result["workspace"]["panels"])
        self.assertIn("map", result["workspace"]["panels"])
        self.assertEqual(result["workspace"]["map"]["mode"], "raster_bounds")
        self.assertEqual(result["views"]["panels"]["raster"]["kind"], "raster_statistics")
        self.assertEqual(result["views"]["panels"]["map"]["mode"], "raster_bounds")
        self.assertEqual(result["views"]["panels"]["map"]["bounds"], [114.0, 30.0, 115.0, 31.0])

    def test_view_model_summarizes_overview_panel_without_frontend_step_scans(self):
        from result_contract import build_result_contract

        result = build_result_contract({
            "run_id": "overview-view",
            "status": "COMPLETED",
            "result_type": "spatial_overview_result",
            "answer": "已完成",
            "steps": [
                {"id": "admin", "tool": "range_query", "status": "COMPLETED", "result": {"dataset": "admin_areas", "result_ref": "memory://admin"}},
                {"id": "roads", "tool": "get_zonal_vector_summary", "status": "COMPLETED", "result": {"dataset": "roads", "summary": {"feature_count": 12}}},
            ],
            "_geometry_evidence": {
                "status": "real_geometry",
                "reason": "导出摘要包含真实空间要素",
                "feature_count": 13,
                "sources": ["geojson"],
            },
            "geojson_ref": "outputs/geojson/overview.geojson",
        })

        overview = result["views"]["panels"]["overview"]
        self.assertEqual(overview["kind"], "spatial_overview")
        self.assertIn("数据来源", [item["label"] for item in overview["metrics"]])
        self.assertEqual(result["views"]["panels"]["map"]["mode"], "geojson")

    def test_view_model_summarizes_complex_result_panels(self):
        from result_contract import build_result_contract

        health = build_result_contract({
            "run_id": "health-view",
            "status": "COMPLETED",
            "result_type": "dataset_health_result",
            "answer": "已完成",
            "steps": [
                {
                    "id": "health",
                    "tool": "get_dataset_health_report",
                    "status": "COMPLETED",
                    "result": {
                        "status": "degraded",
                        "core_status": "ready",
                        "optional_status": "degraded",
                        "warning": "道路数据缺失",
                        "datasets": [
                            {"dataset": "dem", "status": "ready", "file_count": 2, "usable_for": ["get_raster_statistics"]},
                            {"dataset": "roads", "status": "degraded", "feature_count": 0, "checks": [{"status": "warning", "message": "empty"}]},
                        ],
                    },
                }
            ],
        })
        health_view = health["views"]["panels"]["health"]
        self.assertEqual(health_view["kind"], "dataset_health")
        self.assertIn("核心数据", [item["label"] for item in health_view["metrics"]])
        self.assertEqual(len(health_view["rows"]), 2)

        composite = build_result_contract({
            "run_id": "composite-view",
            "status": "COMPLETED",
            "result_type": "spatial_analysis_result",
            "answer": "已完成",
            "steps": [
                {"id": "elevation", "tool": "get_zonal_raster_statistics", "status": "COMPLETED", "result": {"dataset": "dem", "statistics": {"mean": 42}}},
                {"id": "slope", "tool": "get_zonal_slope_statistics", "status": "COMPLETED", "result": {"dataset": "slope", "statistics": {"mean": 12}}},
                {"id": "land", "tool": "get_zonal_land_use_distribution", "status": "COMPLETED", "result": {"dataset": "land_use", "statistics": {"category_count": 3, "categories": [{"value": 11, "share": 0.7}]}}},
            ],
        })
        composite_view = composite["views"]["panels"]["composite"]
        self.assertEqual(composite_view["kind"], "spatial_composite")
        self.assertIn("坡度均值（度）", [item["label"] for item in composite_view["metrics"]])
        self.assertEqual(composite_view["categories"][0]["value"], 11)

        buildability = build_result_contract({
            "run_id": "buildability-view",
            "status": "COMPLETED",
            "result_type": "constrained_buildability_result",
            "answer": "已完成",
            "steps": [
                {
                    "id": "buildability",
                    "tool": "get_zonal_buildability_analysis",
                    "status": "COMPLETED",
                    "result": {
                        "statistics": {
                            "candidate_ratio": 0.25,
                            "candidate_pixel_count": 120,
                            "valid_pixel_count": 480,
                            "slope_limit_degrees": 20,
                        },
                        "rules": {"warning": "演示筛选"},
                    },
                }
            ],
        })
        buildability_view = buildability["views"]["panels"]["buildability"]
        self.assertEqual(buildability_view["kind"], "buildability_screening")
        self.assertIn("候选像元比例", [item["label"] for item in buildability_view["metrics"]])
        self.assertEqual(buildability_view["coverage"]["candidate_ratio"], 0.25)

    def test_view_model_summarizes_vector_panels(self):
        from result_contract import build_result_contract

        vector = build_result_contract({
            "run_id": "vector-view",
            "status": "COMPLETED",
            "result_type": "vector_result",
            "answer": "已完成",
            "steps": [
                {
                    "id": "query",
                    "tool": "range_query",
                    "status": "COMPLETED",
                    "result": {
                        "dataset": "roads",
                        "count": 4,
                        "crs": "EPSG:4326",
                        "result_ref": "memory://roads/query",
                        "metrics": {"backend": "in_memory", "source": "demo"},
                    },
                }
            ],
        })

        view = vector["views"]["panels"]["vector"]
        self.assertEqual(view["kind"], "vector_query")
        self.assertIn("要素数", [item["label"] for item in view["metrics"]])
        self.assertEqual(view["rows"][0]["label"], "数据集")

        zonal = build_result_contract({
            "run_id": "zonal-vector-view",
            "status": "COMPLETED",
            "result_type": "zonal_vector_summary_result",
            "answer": "已完成",
            "steps": [
                {
                    "id": "zonal-vector",
                    "tool": "get_zonal_vector_summary",
                    "status": "COMPLETED",
                    "result": {
                        "dataset": "roads",
                        "admin_name": "洪山区",
                        "summary": {
                            "matched_features": 12,
                            "returned_features": 8,
                            "named_features": 3,
                            "category_counts": {"primary": 5, "secondary": 7},
                        },
                    },
                }
            ],
        })
        zonal_view = zonal["views"]["panels"]["vector"]
        self.assertEqual(zonal_view["kind"], "zonal_vector_summary")
        self.assertEqual(zonal_view["table"]["columns"], ["类别", "数量"])
        self.assertEqual(zonal_view["table"]["rows"][0], ["secondary", 7])

    def test_comparison_views_build_chart_panel(self):
        from result_contract import build_comparison_views

        views = build_comparison_views(
            [
                {
                    "run_id": "run-10",
                    "slope_limit_degrees": 10,
                    "candidate_pixel_count": 100,
                    "candidate_ratio": 0.1,
                    "status": "COMPLETED",
                },
                {
                    "run_id": "run-20",
                    "slope_limit_degrees": 20,
                    "candidate_pixel_count": 150,
                    "candidate_ratio": 0.15,
                    "status": "COMPLETED",
                },
            ],
            "buildability_threshold_comparison",
            title="建设适宜性阈值对比",
            x_field="slope_limit_degrees",
            x_label="坡度阈值",
            y_field="candidate_pixel_count",
            y_label="候选像元",
            table_columns=[("坡度", "slope_limit_degrees"), ("候选像元", "candidate_pixel_count")],
        )

        self.assertEqual(views["schema_version"], "spatial-agent.views.v1")
        chart = views["panels"]["chart"]
        self.assertEqual(chart["kind"], "comparison_chart")
        self.assertEqual(chart["chart_type"], "bar")
        self.assertEqual(chart["encodings"]["x"]["field"], "slope_limit_degrees")
        self.assertEqual(chart["series"][0]["points"][1]["label"], "20°")
        self.assertEqual(chart["table"]["columns"], ["坡度", "候选像元"])
        self.assertEqual(chart["table"]["rows"][0], [10, 100])

    def test_workspace_contract_covers_all_catalog_result_types(self):
        from agent.capability_catalog import capability_catalog
        from result_contract import build_result_contract

        for capability in capability_catalog()["capabilities"]:
            for result_type in capability.get("result_types", []):
                with self.subTest(result_type=result_type):
                    result = build_result_contract({
                        "run_id": "workspace-" + result_type,
                        "status": "COMPLETED",
                        "result_type": result_type,
                        "answer": "已完成",
                        "steps": [],
                    })
                    self.assertEqual(
                        result["workspace"]["schema_version"],
                        "spatial-agent.workspace.v1",
                    )
                    self.assertEqual(
                        result["views"]["schema_version"],
                        "spatial-agent.views.v1",
                    )
                    self.assertTrue(result["workspace"]["registered_type"])

    def test_geojson_reference_is_exposed_as_spatial_evidence(self):
        payload = AgentService().run(
            "查询洪山区行政区边界",
            backend="memory",
            export_geojson=True,
        )

        result = payload["result"]
        self.assertFalse(result["geometry"]["available"])
        self.assertEqual(result["geometry"]["status"], "no_geometry")
        self.assertEqual(result["references"][-1]["kind"], "geojson")
        self.assertTrue(result["geometry"]["geojson_ref"])

    def test_contract_does_not_include_raw_geometry(self):
        payload = AgentService().run("你好", backend="memory")

        serialized = str(payload["result"])
        self.assertNotIn("coordinates", serialized)
        self.assertNotIn("_candidate_geometry", serialized)

    def test_core_evaluation_checks_result_types_and_contract_integrity(self):
        cases = __import__("json").loads(
            (Path(__file__).parents[1] / "evaluation" / "cases" / "core-workflows.json").read_text(
                encoding="utf-8"
            )
        )
        report = run_cases(build_runtime("rule", "memory"), cases)

        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["result_type_match_rate"], 1.0)
        self.assertEqual(report["result_contract_valid_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
