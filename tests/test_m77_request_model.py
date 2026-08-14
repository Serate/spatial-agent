import unittest

from agent.capability_routing import CapabilityRouter
from agent.planner import RuleBasedPlanner
from agent.request_model import parse_spatial_request


COMPLEX_REQUEST = (
    "请对洪山区进行综合空间分析：查询行政区边界，统计DEM高程与坡度，"
    "分析土地利用分布，汇总道路和水体，并筛选坡度不超过20度、"
    "距离道路不超过1000米且排除水体的建设候选区域。"
)


class M77SpatialRequestTests(unittest.TestCase):
    def test_extracts_entities_tasks_constraints_and_evidence(self):
        parsed = parse_spatial_request(COMPLEX_REQUEST)

        self.assertEqual(parsed.admin_name, "洪山区")
        self.assertEqual(
            set(parsed.tasks),
            {"admin_boundary", "elevation", "slope", "land_use", "roads", "water", "buildability"},
        )
        self.assertEqual(parsed.constraints["slope_max"], 20.0)
        self.assertEqual(parsed.constraints["road_distance_max"], 1000.0)
        self.assertTrue(parsed.constraints["exclude_water"])
        self.assertIn("geometry", parsed.evidence)

    def test_admin_extraction_is_region_and_phrase_independent(self):
        cases = (
            ("针对江夏区进行建设适宜性筛选", "江夏区"),
            ("关于蔡甸区的空间概况", "蔡甸区"),
            ("在武昌区查询道路", "武昌区"),
        )
        for request, expected in cases:
            with self.subTest(request=request):
                self.assertEqual(parse_spatial_request(request).admin_name, expected)

    def test_planner_uses_clean_area_for_complex_request(self):
        plan = RuleBasedPlanner().plan(COMPLEX_REQUEST)
        constrained = plan.steps[-1]

        self.assertEqual(constrained.tool, "get_zonal_constrained_buildability_analysis")
        self.assertEqual(
            constrained.args["admin_name"],
            {"$from": "filter-admin", "path": "first_name"},
        )
        self.assertEqual(constrained.args["slope_limit_degrees"], 20.0)
        self.assertEqual(constrained.args["road_distance_m"], 1000.0)
        self.assertTrue(constrained.args["exclude_water"])

    def test_capability_router_selects_capability_before_plan_building(self):
        parsed = parse_spatial_request(COMPLEX_REQUEST)
        selected = CapabilityRouter().select(COMPLEX_REQUEST, parsed)

        self.assertEqual(selected[0].capability_id, "spatial_analysis")
        self.assertIn("composition", selected[0].signals)
        self.assertIn("buildability", selected[0].tasks)

    def test_buildability_variant_uses_generic_route(self):
        request = "洪山区有哪些地方适合建设"
        parsed = parse_spatial_request(request)
        selected = CapabilityRouter().select(request, parsed)

        self.assertIn("buildability", parsed.tasks)
        self.assertEqual(parsed.admin_name, "洪山区")
        self.assertEqual(selected[0].capability_id, "zonal_terrain_land_use")

    def test_runtime_completes_composed_request_and_composes_actual_results(self):
        from run_demo import build_runtime

        result = build_runtime("rule", "memory").run(COMPLEX_REQUEST)

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "spatial_analysis_result")
        self.assertEqual(len(result.steps), 9)
        self.assertTrue(all(step.status == "COMPLETED" for step in result.steps))
        self.assertIn("已完成 9 个工具步骤", result.answer)
        self.assertIn("高程", result.answer)
        self.assertIn("建设候选", result.answer)

    def test_composed_answer_reports_failed_and_blocked_steps(self):
        from agent.answer_composer import AnswerComposer
        from agent.models import StepRun

        steps = [
            StepRun("health", "get_dataset_health_report", {}, status="COMPLETED", result={"status": "degraded"}),
            StepRun("slope", "get_zonal_slope_statistics", {}, status="FAILED", error="DEM unavailable"),
            StepRun("buildability", "get_zonal_buildability_analysis", {}, status="BLOCKED", error="blocked"),
        ]
        answer = AnswerComposer()._compose_spatial_analysis_result(steps)

        self.assertIn("1 个步骤失败", answer)
        self.assertIn("1 个后续步骤因依赖失败而未执行", answer)
        self.assertIn("DEM unavailable", answer)


if __name__ == "__main__":
    unittest.main()
