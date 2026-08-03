import re
from typing import Protocol

from .errors import ClarificationNeeded, RequestRejected
from .models import PlanStep, TaskPlan


class Planner(Protocol):
    def plan(self, request: str) -> TaskPlan:
        ...


class RuleBasedPlanner:
    """A deterministic Planner Adapter for M1 and contract tests."""

    DELETE_TERMS = ("\u5220\u9664", "\u5168\u4e2d\u56fd", "\u4efb\u610f SQL", "\u5bfc\u51fa\u5168\u90e8")
    KNN_TERMS = ("\u6700\u8fd1", "KNN")
    ROAD_TERMS = ("\u9053\u8def", "\u4e3b\u5e72\u9053")
    SLOPE_TERM = "\u5761\u5ea6"
    HIGH_SLOPE_TERM = "\u9ad8\u5761\u5ea6"
    SLOPE_PATTERN = re.compile(r"\u5761\u5ea6(?:\u8d85\u8fc7|\u5927\u4e8e)\s*(\d+)\s*\u5ea6")
    DISTANCE_PATTERN = re.compile(r"(\d+)\s*\u7c73")

    def plan(self, request: str) -> TaskPlan:
        if not request.strip():
            raise ClarificationNeeded("empty spatial analysis request")
        if any(term in request for term in self.DELETE_TERMS):
            raise RequestRejected("request contains destructive, unauthorized, or oversized operations")
        if any(term in request.upper() for term in self.KNN_TERMS):
            raise ClarificationNeeded("M1 does not support KNN yet; use an explicit range condition")

        slope_match = self.SLOPE_PATTERN.search(request)
        mentions_slope = self.SLOPE_TERM in request or self.HIGH_SLOPE_TERM in request
        if mentions_slope and slope_match is None:
            raise ClarificationNeeded("missing slope threshold, for example: slope greater than 25 degrees")

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
