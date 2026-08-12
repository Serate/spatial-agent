import re
from typing import Any, Mapping, Optional, Protocol

from .errors import ClarificationNeeded, RequestRejected
from .models import PlanStep, TaskPlan
from .spatial_intent import clarification_details, clarification_message, classify_spatial_intent
from .workflow_templates import workflow_request_hint


class Planner(Protocol):
    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        ...


class RuleBasedPlanner:
    """A deterministic Planner Adapter for M1 and contract tests."""

    GREETING_TERMS = ("你好", "您好", "嗨", "hello", "hi")

    DELETE_TERMS = ("\u5220\u9664", "\u5168\u4e2d\u56fd", "\u4efb\u610f SQL", "\u5bfc\u51fa\u5168\u90e8")
    KNN_TERMS = ("\u6700\u8fd1", "KNN")
    ROAD_TERMS = ("\u9053\u8def", "\u4e3b\u5e72\u9053")
    SLOPE_TERM = "\u5761\u5ea6"
    HIGH_SLOPE_TERM = "\u9ad8\u5761\u5ea6"
    SLOPE_PATTERN = re.compile(r"\u5761\u5ea6(?:\u8d85\u8fc7|\u5927\u4e8e)\s*(\d+)\s*\u5ea6")
    DISTANCE_PATTERN = re.compile(r"(\d+)\s*\u7c73")
    ADMIN_NAME_PATTERN = re.compile(
        r"([\u4e00-\u9fff]{2,12}(?:\u81ea\u6cbb\u53bf|\u6797\u533a|\u5e02|\u53bf|\u533a))"
    )
    ADMIN_TERMS = ("\u884c\u653f\u533a", "\u8fb9\u754c", "\u53bf\u57df", "\u884c\u653f\u8303\u56f4", "\u533a\u5212")
    ADMIN_GENERIC_NAMES = ("\u884c\u653f\u533a", "\u53bf\u57df")
    QUERY_PREFIXES = ("\u67e5\u8be2", "\u67e5\u627e", "\u67e5\u770b", "\u83b7\u53d6", "\u7edf\u8ba1", "\u5206\u6790", "\u5e2e\u6211", "\u8bf7")
    ADMIN_DESCRIPTIVE_SUFFIXES = ("\u884c\u653f\u533a", "\u53bf\u57df", "\u8fb9\u754c")
    RASTER_METADATA_TERMS = ("\u5143\u6570\u636e", "\u6805\u683c", "\u50cf\u5143", "\u5f71\u50cf", "metadata")
    RASTER_STATISTICS_TERMS = ("\u7edf\u8ba1", "\u5206\u6790", "\u5747\u503c", "\u5e73\u5747", "\u6700\u5c0f", "\u6700\u5927", "\u9ad8\u7a0b\u6982\u51b5", "\u5206\u5e03", "\u60c5\u51b5", "\u5982\u4f55", "\u600e\u4e48\u6837", "\u6982\u51b5")
    DEM_TERMS = ("DEM", "dem", "\u9ad8\u7a0b", "\u5730\u5f62")
    LAND_USE_TERMS = ("\u571f\u5730\u5229\u7528", "\u571f\u5730\u8986\u76d6", "\u8986\u76d6\u60c5\u51b5", "\u5730\u7c7b", "land use", "land_use")
    BUILDABILITY_TERMS = ("\u5efa\u8bbe\u9002\u5b9c\u6027", "\u9002\u5b9c\u5efa\u8bbe", "\u9002\u5408\u5efa\u8bbe", "\u53ef\u5efa\u8bbe", "\u9002\u5408\u5f00\u53d1", "\u5efa\u8bbe\u6f5c\u529b", "\u5efa\u8bbe\u5019\u9009", "\u5efa\u8bbe\u7b5b\u9009", "\u5efa\u8bbe\u7528\u5730")
    BUILDABILITY_SLOPE_PATTERN = re.compile(r"\u5761\u5ea6(?:\u4e0d\u8d85\u8fc7|\u4e0d\u5927\u4e8e|\u5c0f\u4e8e|\u4f4e\u4e8e|\u9608\u503c\u4e3a)\s*(\d+(?:\.\d+)?)\s*\u5ea6")
    HEALTH_TERMS = ("\u6570\u636e\u8d28\u91cf", "\u6570\u636e\u5065\u5eb7", "\u6570\u636e\u68c0\u67e5", "\u6570\u636e\u53ef\u7528", "\u662f\u5426\u53ef\u7528", "\u53ef\u7528\u6027", "\u6570\u636e\u72b6\u6001", "\u6570\u636e\u5b8c\u6574\u6027", "\u6570\u636e\u8bca\u65ad")

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        request = workflow_request_hint(request, workflow)
        if not request.strip():
            raise ClarificationNeeded("empty spatial analysis request")
        if any(term in request for term in self.DELETE_TERMS):
            raise RequestRejected("request contains destructive, unauthorized, or oversized operations")
        if any(term in request.upper() for term in self.KNN_TERMS):
            raise ClarificationNeeded("M1 does not support KNN yet; use an explicit range condition")

        if request.strip().lower() in self.GREETING_TERMS:
            return TaskPlan(
                goal="respond to greeting",
                steps=[],
                output={
                    "type": "direct_answer",
                    "message": "你好，我是空间智能体。你可以直接询问行政区边界、DEM 高程、坡度、土地利用或建设适宜性演示分析。",
                },
            )

        if any(term in request for term in ("你能做什么", "帮助", "能力范围", "你是谁")):
            return TaskPlan(
                goal="explain spatial agent capabilities",
                steps=[],
                output={
                    "type": "direct_answer",
                    "message": "我是空间智能体，可以查询行政区边界，分析 DEM 高程和坡度，统计土地利用，并进行建设适宜性演示筛选。需要真实栅格分析时，请选择本地 GIS 后端。",
                },
            )

        health_plan = self._try_dataset_health_plan(request)
        if health_plan is not None:
            return health_plan

        constrained_plan = self._try_constrained_buildability_plan(request)
        if constrained_plan is not None:
            return constrained_plan

        terrain_plan = self._try_terrain_land_use_plan(request)
        if terrain_plan is not None:
            return terrain_plan

        composite_plan = self._try_composite_admin_raster_plan(request)
        if composite_plan is not None:
            return composite_plan

        overview_plan = self._try_spatial_overview_plan(request)
        if overview_plan is not None:
            return overview_plan

        zonal_vector_plan = self._try_zonal_vector_plan(request)
        if zonal_vector_plan is not None:
            return zonal_vector_plan

        vector_relation_plan = self._try_vector_relation_plan(request)
        if vector_relation_plan is not None:
            return vector_relation_plan

        vector_plan = self._try_vector_query_plan(request)
        if vector_plan is not None:
            return vector_plan

        zonal_plan = self._try_zonal_raster_plan(request)
        if zonal_plan is not None:
            return zonal_plan

        raster_statistics_plan = self._try_raster_statistics_plan(request)
        if raster_statistics_plan is not None:
            return raster_statistics_plan

        raster_metadata_plan = self._try_raster_metadata_plan(request)
        if raster_metadata_plan is not None:
            return raster_metadata_plan

        admin_plan = self._try_admin_area_plan(request)
        if admin_plan is not None:
            return admin_plan

        slope_match = self.SLOPE_PATTERN.search(request)
        mentions_slope = self.SLOPE_TERM in request or self.HIGH_SLOPE_TERM in request
        if mentions_slope and slope_match is None:
            raise ClarificationNeeded("missing slope threshold, for example: slope greater than 25 degrees")

        intent = classify_spatial_intent(request)
        if intent["is_spatial"] and slope_match is None:
            raise ClarificationNeeded(clarification_message(request), clarification_details(request))

        if not any(term in request for term in self.ROAD_TERMS) or slope_match is None:
            raise ClarificationNeeded("M1 requires a road condition and an explicit slope threshold")

        distance_match = self.DISTANCE_PATTERN.search(request)
        if distance_match is None:
            raise ClarificationNeeded("missing road distance, for example: within 500 meters of roads")

        slope_limit = int(slope_match.group(1))
        distance_m = int(distance_match.group(1))
        steps = [
            PlanStep("schema-roads", "get_dataset_schema", {"dataset": "roads"}),
            PlanStep("schema-slope", "get_dataset_schema", {"dataset": "slope"}),
            PlanStep(
                "filter-slope",
                "range_query",
                {
                    "dataset": "slope",
                    "conditions": [
                        {"field": "slope_degree", "operator": "gt", "value": slope_limit}
                    ],
                    "limit": 10000,
                },
                ["schema-slope"],
            ),
            PlanStep(
                "near-roads",
                "spatial_join",
                {
                    "left_dataset": "roads",
                    "right_dataset": "slope",
                    "relation": "near",
                    "distance_m": distance_m,
                },
                ["schema-roads", "filter-slope"],
            ),
        ]
        return TaskPlan(
            goal="identify high-slope spatial areas near roads",
            steps=steps,
            output={"type": "spatial_result", "summary": True},
        )

    def _try_dataset_health_plan(self, request: str):
        if not any(term in request for term in self.HEALTH_TERMS):
            return None
        if any(term in request for term in ("\u9053\u8def", "\u8def\u7f51", "\u4e3b\u5e72\u9053")):
            dataset = "roads"
        elif any(term in request for term in ("\u6c34\u4f53", "\u6cb3\u6d41", "\u6e56\u6cca", "\u6c34\u7cfb")):
            dataset = "water"
        elif any(term in request for term in ("DEM", "dem", "\u9ad8\u7a0b", "\u5730\u5f62")):
            dataset = "dem"
        elif any(term in request for term in ("\u571f\u5730\u5229\u7528", "\u571f\u5730\u8986\u76d6", "\u5730\u7c7b")):
            dataset = "land_use"
        elif any(term in request for term in ("\u884c\u653f\u533a", "\u8fb9\u754c")):
            dataset = "admin_areas"
        else:
            dataset = "all"
        return TaskPlan(
            goal="check configured spatial dataset health",
            steps=[PlanStep("dataset-health", "get_dataset_health_report", {"dataset": dataset, "max_files": 10})],
            output={"type": "dataset_health_result", "summary": True},
        )

    def _try_admin_area_plan(self, request: str):
        if not any(term in request for term in self.ADMIN_TERMS):
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        admin_name = self._clean_admin_name(match.group(1))
        if not admin_name or admin_name in self.ADMIN_GENERIC_NAMES:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        steps = [
            PlanStep("schema-admin", "get_dataset_schema", {"dataset": "admin_areas"}),
            PlanStep(
                "filter-admin",
                "range_query",
                {
                    "dataset": "admin_areas",
                    "conditions": [{"field": "name", "operator": "eq", "value": admin_name}],
                    "limit": 100,
                },
                ["schema-admin"],
            ),
        ]
        return TaskPlan(
            goal="query admin area boundary by name",
            steps=steps,
            output={"type": "admin_area_result", "summary": True},
        )

    def _try_vector_query_plan(self, request: str):
        if self.SLOPE_TERM in request or any(term in request for term in ("距离", "附近", "以内", "邻近")):
            return None
        road_terms = ("道路", "路网", "主干道", "高速", "公路")
        water_terms = ("水体", "河流", "湖泊", "水系")
        if any(term in request for term in water_terms):
            dataset = "water"
            goal = "query OSM water features"
        elif any(term in request for term in road_terms):
            dataset = "roads"
            goal = "query OSM road features"
        else:
            return None
        conditions = []
        if dataset == "roads":
            highway_match = re.search(r"(motorway|trunk|primary|secondary|tertiary|residential)", request, re.IGNORECASE)
            if highway_match:
                conditions.append({"field": "highway", "operator": "eq", "value": highway_match.group(1).lower()})
        return TaskPlan(
            goal=goal,
            steps=[
                PlanStep("schema-vector", "get_dataset_schema", {"dataset": dataset}),
                PlanStep(
                    "filter-vector",
                    "range_query",
                    {"dataset": dataset, "conditions": conditions, "limit": 10000},
                    ["schema-vector"],
                ),
            ],
            output={"type": "vector_result", "summary": True},
        )

    def _try_zonal_vector_plan(self, request: str):
        road_terms = ("道路", "路网", "主干道", "高速", "公路")
        water_terms = ("水体", "河流", "湖泊", "水系")
        if any(term in request for term in water_terms):
            dataset = "water"
        elif any(term in request for term in road_terms):
            dataset = "roads"
        else:
            return None
        wuhan_names = ("洪山区", "江岸区", "武昌区", "汉阳区", "硚口区", "江汉区", "汉南区", "东西湖区", "青山区", "新洲区", "黄陂区", "江夏区", "蔡甸区")
        if not any(name in request for name in wuhan_names):
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            return None
        admin_name = self._clean_admin_name(match.group(1))
        return TaskPlan(
            goal="summarize OSM vector features inside an administrative area",
            steps=[
                PlanStep(
                    "zonal-vector",
                    "get_zonal_vector_summary",
                    {"dataset": dataset, "admin_name": admin_name, "max_features": 10000},
                )
            ],
            output={"type": "zonal_vector_result", "summary": True},
        )

    def _try_vector_relation_plan(self, request: str):
        road_terms = ("道路", "路网", "主干道", "高速", "公路")
        water_terms = ("水体", "河流", "湖泊", "水系")
        if not any(term in request for term in road_terms) or not any(term in request for term in water_terms):
            return None
        distance_match = self.DISTANCE_PATTERN.search(request)
        if distance_match is None:
            raise ClarificationNeeded("missing distance, for example: within 500 meters")
        distance_m = int(distance_match.group(1))
        return TaskPlan(
            goal="find water features near roads",
            steps=[
                PlanStep("schema-roads", "get_dataset_schema", {"dataset": "roads"}),
                PlanStep("schema-water", "get_dataset_schema", {"dataset": "water"}),
                PlanStep(
                    "near-water",
                    "spatial_join",
                    {
                        "left_dataset": "roads",
                        "right_dataset": "water",
                        "relation": "near",
                        "distance_m": distance_m,
                    },
                    ["schema-roads", "schema-water"],
                ),
            ],
            output={"type": "spatial_relation_result", "summary": True},
        )

    def _try_constrained_buildability_plan(self, request: str):
        if not any(term in request for term in self.BUILDABILITY_TERMS):
            return None
        road_terms = ("道路", "路网", "主干道", "公路")
        water_terms = ("水体", "河流", "湖泊", "水系")
        has_road_constraint = any(term in request for term in road_terms)
        has_water_constraint = any(term in request for term in water_terms)
        if not has_road_constraint and not has_water_constraint:
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        admin_name = self._clean_admin_name(match.group(1))
        slope_match = self.BUILDABILITY_SLOPE_PATTERN.search(request)
        slope_limit = float(slope_match.group(1)) if slope_match else 15.0
        distance_match = self.DISTANCE_PATTERN.search(request)
        if has_road_constraint and distance_match is None:
            raise ClarificationNeeded("missing road distance, for example: within 500 meters of roads")
        distance_m = float(distance_match.group(1)) if distance_match else 500.0
        return TaskPlan(
            goal="screen construction candidates with raster and vector constraints",
            steps=[
                PlanStep(
                    "dataset-health",
                    "get_dataset_health_report",
                    {"dataset": "all", "max_files": 10},
                ),
                PlanStep(
                    "constrained-buildability",
                    "get_zonal_constrained_buildability_analysis",
                    {
                        "admin_name": admin_name,
                        "slope_limit_degrees": slope_limit,
                        "road_distance_m": distance_m,
                        "exclude_water": has_water_constraint,
                        "max_files": 10,
                    },
                    ["dataset-health"],
                )
            ],
            output={"type": "constrained_buildability_result", "summary": True},
        )

    def _try_raster_metadata_plan(self, request: str):
        dataset = None
        if any(term in request for term in self.DEM_TERMS):
            dataset = "dem"
        elif any(term in request for term in self.LAND_USE_TERMS):
            dataset = "land_use"

        if dataset is None:
            return None
        if not any(term in request for term in self.RASTER_METADATA_TERMS):
            return None

        return TaskPlan(
            goal="inspect raster dataset metadata",
            steps=[
                PlanStep(
                    "raster-metadata",
                    "get_raster_metadata",
                    {"dataset": dataset, "max_files": 3},
                )
            ],
            output={"type": "raster_metadata_result", "summary": True},
        )

    def _try_raster_statistics_plan(self, request: str):
        dataset = None
        if any(term in request for term in self.DEM_TERMS):
            dataset = "dem"
        elif any(term in request for term in self.LAND_USE_TERMS):
            dataset = "land_use"
        if dataset is None or not any(term in request for term in self.RASTER_STATISTICS_TERMS):
            return None
        return TaskPlan(
            goal="analyze raster value statistics",
            steps=[
                PlanStep(
                    "raster-statistics",
                    "get_raster_statistics",
                    {"dataset": dataset, "max_files": 3},
                )
            ],
            output={"type": "raster_statistics_result", "summary": True},
        )

    def _try_zonal_raster_plan(self, request: str):
        if not any(term in request for term in self.ADMIN_TERMS) and not self.ADMIN_NAME_PATTERN.search(request):
            return None
        if not any(term in request for term in self.DEM_TERMS + self.LAND_USE_TERMS):
            return None
        if not any(term in request for term in self.RASTER_STATISTICS_TERMS):
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        admin_name = self._clean_admin_name(match.group(1))
        dataset = "dem" if any(term in request for term in self.DEM_TERMS) else "land_use"
        return TaskPlan(
            goal="analyze raster statistics inside an administrative area",
            steps=[
                PlanStep(
                    "dataset-health",
                    "get_dataset_health_report",
                    {"dataset": dataset, "max_files": 10},
                ),
                PlanStep(
                    "zonal-raster-statistics",
                    "get_zonal_raster_statistics",
                    {"dataset": dataset, "admin_name": admin_name, "max_files": 10},
                    ["dataset-health"],
                )
            ],
            output={"type": "zonal_raster_statistics_result", "summary": True},
        )

    def _try_composite_admin_raster_plan(self, request: str):
        if not ("并" in request and "边界" in request):
            return None
        if not any(term in request for term in self.DEM_TERMS + self.LAND_USE_TERMS):
            return None
        if not any(term in request for term in self.RASTER_STATISTICS_TERMS):
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        admin_name = self._clean_admin_name(match.group(1))
        dataset = "dem" if any(term in request for term in self.DEM_TERMS) else "land_use"
        return TaskPlan(
            goal="resolve administrative area and analyze raster statistics",
            steps=[
                PlanStep(
                    "dataset-health",
                    "get_dataset_health_report",
                    {"dataset": dataset, "max_files": 10},
                ),
                PlanStep("schema-admin", "get_dataset_schema", {"dataset": "admin_areas"}, ["dataset-health"]),
                PlanStep(
                    "filter-admin",
                    "range_query",
                    {
                        "dataset": "admin_areas",
                        "conditions": [{"field": "name", "operator": "eq", "value": admin_name}],
                        "limit": 100,
                    },
                    ["schema-admin"],
                ),
                PlanStep(
                    "zonal-raster-statistics",
                    "get_zonal_raster_statistics",
                    {
                        "dataset": dataset,
                        "admin_name": {"$from": "filter-admin", "path": "first_name"},
                        "max_files": 10,
                    },
                    ["filter-admin"],
                ),
            ],
            output={"type": "zonal_raster_statistics_result", "summary": True},
        )

    def _try_spatial_overview_plan(self, request: str):
        overview_terms = ("空间概况", "空间总览", "整体空间分析", "综合空间概览", "全面分析")
        if not any(term in request for term in overview_terms):
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        admin_name = self._clean_admin_name(match.group(1))
        area_ref = {"$from": "filter-admin", "path": "first_name"}
        steps = [
            PlanStep("dataset-health", "get_dataset_health_report", {"dataset": "all", "max_files": 10}),
            PlanStep("schema-admin", "get_dataset_schema", {"dataset": "admin_areas"}, ["dataset-health"]),
            PlanStep(
                "filter-admin", "range_query",
                {"dataset": "admin_areas", "conditions": [{"field": "name", "operator": "eq", "value": admin_name}], "limit": 100},
                ["schema-admin"],
            ),
            PlanStep("overview-elevation", "get_zonal_raster_statistics", {"dataset": "dem", "admin_name": area_ref, "max_files": 10}, ["filter-admin"]),
            PlanStep("overview-slope", "get_zonal_slope_statistics", {"admin_name": area_ref, "max_files": 10}, ["filter-admin"]),
            PlanStep("overview-land-use", "get_zonal_land_use_distribution", {"admin_name": area_ref, "max_files": 10}, ["filter-admin"]),
            PlanStep("overview-roads", "get_zonal_vector_summary", {"dataset": "roads", "admin_name": area_ref, "max_features": 10000}, ["filter-admin"]),
            PlanStep("overview-water", "get_zonal_vector_summary", {"dataset": "water", "admin_name": area_ref, "max_features": 10000}, ["filter-admin"]),
        ]
        return TaskPlan(
            goal="build a cross-source spatial overview for an administrative area",
            steps=steps,
            output={"type": "spatial_overview_result", "summary": True},
        )

    def _try_terrain_land_use_plan(self, request: str):
        """Plan a real multi-source terrain overview for an administrative area."""
        has_area = any(term in request for term in self.ADMIN_TERMS) or self.ADMIN_NAME_PATTERN.search(request)
        is_buildability = any(term in request for term in self.BUILDABILITY_TERMS)
        has_slope = self.SLOPE_TERM in request or any(term in request for term in ("地形", "建设", "适合"))
        has_land_use = any(term in request for term in self.LAND_USE_TERMS)
        has_dem = any(term in request for term in self.DEM_TERMS)
        if is_buildability:
            has_slope = has_land_use = has_dem = True
        if not (has_area and has_slope and has_land_use and has_dem):
            return None
        match = self.ADMIN_NAME_PATTERN.search(request)
        if match is None:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        admin_name = self._clean_admin_name(match.group(1))
        slope_match = self.BUILDABILITY_SLOPE_PATTERN.search(request)
        slope_limit = float(slope_match.group(1)) if slope_match else 15.0
        steps = [
                PlanStep("dataset-health", "get_dataset_health_report", {"dataset": "all", "max_files": 10}),
                PlanStep("schema-admin", "get_dataset_schema", {"dataset": "admin_areas"}, ["dataset-health"]),
                PlanStep(
                    "filter-admin", "range_query",
                    {"dataset": "admin_areas", "conditions": [{"field": "name", "operator": "eq", "value": admin_name}], "limit": 100},
                    ["schema-admin"],
                ),
                PlanStep(
                    "zonal-elevation", "get_zonal_raster_statistics",
                    {"dataset": "dem", "admin_name": {"$from": "filter-admin", "path": "first_name"}, "max_files": 10},
                    ["filter-admin"],
                ),
                PlanStep(
                    "zonal-slope", "get_zonal_slope_statistics",
                    {"admin_name": {"$from": "filter-admin", "path": "first_name"}, "max_files": 10},
                    ["filter-admin"],
                ),
                PlanStep(
                    "zonal-land-use", "get_zonal_land_use_distribution",
                    {"admin_name": {"$from": "filter-admin", "path": "first_name"}, "max_files": 10},
                    ["filter-admin"],
                ),
            ]
        if "建设" in request or "适合" in request:
            steps.append(
                PlanStep(
                    "buildability-screening", "get_zonal_buildability_analysis",
                    {"admin_name": {"$from": "filter-admin", "path": "first_name"}, "max_files": 10, "slope_limit_degrees": slope_limit},
                    ["filter-admin"],
                )
            )
        return TaskPlan(
            goal="analyze elevation, derived slope, land-use distribution, and demo buildability screening inside an administrative area",
            steps=steps,
            output={"type": "terrain_land_use_analysis_result", "summary": True},
        )

    def _clean_admin_name(self, value: str) -> str:
        name = value
        for prefix in self.QUERY_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix) :]
        changed = True
        while changed:
            changed = False
            for suffix in self.ADMIN_DESCRIPTIVE_SUFFIXES:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    changed = True
        return name
