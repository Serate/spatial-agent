"""M166: an explicit workflow must control the Domain Planner output contract."""

from __future__ import annotations

import unittest

from agent.service import AgentService


class M166WorkflowSelectionTests(unittest.TestCase):
    def test_explicit_spatial_analysis_compiles_the_selected_workflow(self):
        service = AgentService()
        try:
            preview = service.preview(
                request="进行空间分析",
                session_id="m166-explicit-workflow",
                planner="rule",
                backend="memory",
                workflow={
                    "template_id": "spatial_analysis",
                    "constraints": {"admin_name": "洪山区"},
                },
            )
        finally:
            service.close()

        self.assertEqual(preview["status"], "PLANNED")
        self.assertEqual(preview["result_type"], "spatial_analysis_result")
        self.assertEqual(
            preview["plan"]["output"]["type"],
            "spatial_analysis_result",
        )
        self.assertEqual(
            [step["tool"] for step in preview["plan"]["steps"]],
            [
                "get_dataset_health_report",
                "get_dataset_schema",
                "range_query",
                "get_zonal_raster_statistics",
                "get_zonal_slope_statistics",
                "get_zonal_land_use_distribution",
                "get_zonal_vector_summary",
                "get_zonal_vector_summary",
                "get_zonal_constrained_buildability_analysis",
            ],
        )


if __name__ == "__main__":
    unittest.main()
