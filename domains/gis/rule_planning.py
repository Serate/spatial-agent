"""GIS-owned deterministic plan composition.

The generic Agent Runtime consumes the Planner protocol and TaskPlan contract;
the capability routes and GIS workflow builders live in this Domain Pack.
"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional

from agent.errors import ClarificationNeeded
from agent.models import PlanStep, TaskPlan
from agent.workflow_templates import compile_workflow_plan, get_workflow_template

from .request_model import SpatialRequest
from .intent import clarification_details, clarification_message, classify_spatial_intent
from .routing import GisCapabilityRouter, contains_any


@dataclass(frozen=True)
class PlanningFacts:
    request: str
    spatial: SpatialRequest


Builder = Callable[[PlanningFacts], TaskPlan]


class RuleBasedPlanComposer:
    """Compose a validated-shaped TaskPlan from GIS request facts."""

    _DISTANCE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*米")
    _SLOPE_PATTERN = re.compile(r"坡度(?:超过|大于)\s*(\d+(?:\.\d+)?)\s*度")

    def __init__(self, router: Optional[GisCapabilityRouter] = None) -> None:
        self.router = router or GisCapabilityRouter()
        self._builders: Dict[str, Builder] = {
            "dataset_health": self._build_health,
            "spatial_analysis": self._build_composed,
            "constrained_buildability_screening": self._build_constrained,
            "zonal_terrain_land_use": self._build_terrain,
            "admin_raster_composite": self._build_admin_raster_composite,
            "spatial_overview": self._build_overview,
            "legacy_road_slope": self._build_legacy_road_slope,
            "vector_relation": self._build_vector_relation,
            "vector_summary": self._build_zonal_vector,
            "vector_query": self._build_vector_query,
            "zonal_raster_statistics": self._build_zonal_raster,
            "raster_metadata": self._build_raster_metadata,
            "raster_statistics": self._build_raster_statistics,
            "admin_boundary_query": self._build_admin_boundary,
        }

    @property
    def rule_ids(self) -> List[str]:
        return self.router.route_ids

    def compose(self, facts: PlanningFacts) -> TaskPlan:
        selected = self.router.select(facts.request, facts.spatial)
        if selected:
            return self.compose_capability(selected[0].capability_id, facts)
        self._clarify_unmatched(facts)
        raise AssertionError("unreachable")

    def compose_capability(self, capability_id: str, facts: PlanningFacts) -> TaskPlan:
        """Compile a Domain-owned catalog selection through the same builders."""
        builder = self._builders.get(str(capability_id or "").strip())
        if builder is None:
            self._clarify_unmatched(facts)
            raise AssertionError("unreachable")
        return builder(facts)

    def compose_workflow(self, workflow: Mapping[str, object]) -> TaskPlan:
        """Compile an explicit Domain workflow without re-routing its request.

        A user-selected workflow is already a structured capability decision.
        Re-running the natural-language router after that decision can produce
        a different result contract, which the generic Runtime must correctly
        reject.  Keep the template compiler as the single source of truth for
        the selected DAG, constraints, evidence, and output type.
        """

        if not isinstance(workflow, Mapping):
            raise TypeError("workflow must be an object")
        template_id = workflow.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError("workflow.template_id must be a non-empty string")
        constraints = workflow.get("constraints", {})
        evidence = workflow.get("evidence")
        return self._template_plan(
            template_id.strip(),
            constraints if isinstance(constraints, Mapping) else {},
            evidence=evidence if isinstance(evidence, Iterable) and not isinstance(evidence, (str, bytes)) else None,
        )

    @staticmethod
    def _has(text: str, terms: Iterable[str]) -> bool:
        return contains_any(text, terms)

    def _template_plan(
        self,
        template_id: str,
        constraints: Mapping[str, object],
        *,
        evidence: Optional[Iterable[str]] = None,
        output_overrides: Optional[Mapping[str, object]] = None,
    ) -> TaskPlan:
        selected_evidence = self._template_evidence(template_id, evidence)
        compiled = compile_workflow_plan(
            template_id,
            constraints,
            evidence=selected_evidence,
            output_overrides=output_overrides,
        )
        steps = [
            PlanStep(
                str(step["id"]),
                str(step["tool"]),
                dict(step["args"]),
                list(step.get("depends_on", [])),
            )
            for step in compiled["steps"]
        ]
        return TaskPlan(
            str(compiled["goal"]),
            steps,
            dict(compiled["output"]),
            list(compiled.get("assumptions", [])),
        )

    @staticmethod
    def _template_evidence(
        template_id: str,
        evidence: Optional[Iterable[str]],
    ) -> Optional[List[str]]:
        if evidence is None:
            return None
        allowed = set(get_workflow_template(template_id).get("evidence_options", []))
        selected = [item for item in evidence if item in allowed]
        return selected or None

    @staticmethod
    def _raster_dataset(spatial: SpatialRequest) -> str:
        if "elevation" in spatial.tasks:
            return "dem"
        if "land_use" in spatial.tasks:
            return "land_use"
        if "slope" in spatial.tasks:
            return "slope"
        return "dem"

    def _build_health(self, facts: PlanningFacts) -> TaskPlan:
        datasets = set(facts.spatial.datasets)
        dataset = next(
            (item for item in ("roads", "water", "dem", "land_use", "admin_areas") if item in datasets),
            "all",
        )
        return TaskPlan("check configured spatial dataset health", [
            PlanStep("dataset-health", "get_dataset_health_report", {"dataset": dataset, "max_files": 10})
        ], {"type": "dataset_health_result", "summary": True})

    def _admin_ref(self) -> Mapping[str, str]:
        return {"$from": "filter-admin", "path": "first_name"}

    def _admin_steps(self, admin_name: str, *, health: bool = True) -> List[PlanStep]:
        steps: List[PlanStep] = []
        if health:
            steps.append(PlanStep("dataset-health", "get_dataset_health_report", {"dataset": "all", "max_files": 10}))
        schema_deps = ["dataset-health"] if health else []
        steps.append(PlanStep("schema-admin", "get_dataset_schema", {"dataset": "admin_areas"}, schema_deps))
        steps.append(PlanStep(
            "filter-admin", "range_query",
            {"dataset": "admin_areas", "conditions": [{"field": "name", "operator": "eq", "value": admin_name}], "limit": 100},
            ["schema-admin"],
        ))
        return steps

    def _build_composed(self, facts: PlanningFacts) -> TaskPlan:
        parsed = facts.spatial
        if self._can_use_full_spatial_analysis_template(parsed):
            return self._template_plan(
                "spatial_analysis",
                self._spatial_analysis_constraints(parsed),
                evidence=parsed.evidence,
                output_overrides={
                    "requested_tasks": list(parsed.tasks),
                    "constraints": dict(parsed.constraints),
                    "evidence": list(parsed.evidence),
                },
            )
        area_ref = self._admin_ref()
        steps = self._admin_steps(parsed.admin_name or "")
        if "elevation" in parsed.tasks:
            steps.append(PlanStep("composed-elevation", "get_zonal_raster_statistics", {"dataset": "dem", "admin_name": area_ref, "max_files": 10}, ["filter-admin"]))
        if "slope" in parsed.tasks:
            steps.append(PlanStep("composed-slope", "get_zonal_slope_statistics", {"admin_name": area_ref, "max_files": 10}, ["filter-admin"]))
        if "land_use" in parsed.tasks:
            steps.append(PlanStep("composed-land-use", "get_zonal_land_use_distribution", {"admin_name": area_ref, "max_files": 10}, ["filter-admin"]))
        if "roads" in parsed.tasks:
            steps.append(PlanStep("composed-roads", "get_zonal_vector_summary", {"dataset": "roads", "admin_name": area_ref, "max_features": 10000}, ["filter-admin"]))
        if "water" in parsed.tasks:
            steps.append(PlanStep("composed-water", "get_zonal_vector_summary", {"dataset": "water", "admin_name": area_ref, "max_features": 10000}, ["filter-admin"]))
        if "buildability" in parsed.tasks:
            constrained = bool({"roads", "water"} & set(parsed.tasks) or {"road_distance_max", "exclude_water"} & set(parsed.constraints))
            tool = "get_zonal_constrained_buildability_analysis" if constrained else "get_zonal_buildability_analysis"
            args = {"admin_name": area_ref, "slope_limit_degrees": float(parsed.constraints.get("slope_max", 15.0)), "max_files": 10}
            if constrained:
                args.update({"road_distance_m": float(parsed.constraints.get("road_distance_max", 1000.0)), "exclude_water": bool(parsed.constraints.get("exclude_water", "water" in parsed.tasks))})
            steps.append(PlanStep("composed-buildability", tool, args, ["filter-admin"]))
        return TaskPlan(
            "compose a multi-task spatial analysis DAG from request facts", steps,
            {"type": "spatial_analysis_result", "summary": True, "requested_tasks": list(parsed.tasks), "constraints": dict(parsed.constraints), "evidence": list(parsed.evidence)},
        )

    @staticmethod
    def _can_use_full_spatial_analysis_template(parsed: SpatialRequest) -> bool:
        full_tasks = {"elevation", "slope", "land_use", "roads", "water", "buildability"}
        return bool(parsed.admin_name and full_tasks.issubset(set(parsed.tasks)))

    @staticmethod
    def _spatial_analysis_constraints(parsed: SpatialRequest) -> Dict[str, object]:
        return {
            "admin_name": parsed.admin_name or "",
            "slope_limit_degrees": float(parsed.constraints.get("slope_max", 15.0)),
            "road_distance_m": float(parsed.constraints.get("road_distance_max", 1000.0)),
            "exclude_water": bool(parsed.constraints.get("exclude_water", "water" in parsed.tasks)),
        }

    def _build_constrained(self, facts: PlanningFacts) -> TaskPlan:
        parsed = facts.spatial
        if not parsed.admin_name:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        has_road = "roads" in parsed.tasks
        distance = parsed.constraints.get("road_distance_max")
        if has_road and distance is None:
            raise ClarificationNeeded("missing road distance, for example: within 500 meters of roads")
        return self._template_plan(
            "constrained_buildability",
            {
                "admin_name": parsed.admin_name,
                "slope_limit_degrees": float(parsed.constraints.get("slope_max", 15.0)),
                "road_distance_m": float(distance if distance is not None else 500.0),
                "exclude_water": bool(parsed.constraints.get("exclude_water") or "water" in parsed.tasks),
            },
            evidence=parsed.evidence,
        )

    def _build_terrain(self, facts: PlanningFacts) -> TaskPlan:
        parsed = facts.spatial
        if "buildability" in parsed.tasks:
            tasks = {"elevation", "slope", "land_use"}
        else:
            tasks = set(parsed.tasks)
        steps = self._admin_steps(parsed.admin_name or "")
        ref = self._admin_ref()
        if "elevation" in tasks:
            steps.append(PlanStep("zonal-elevation", "get_zonal_raster_statistics", {"dataset": "dem", "admin_name": ref, "max_files": 10}, ["filter-admin"]))
        if "slope" in tasks:
            steps.append(PlanStep("zonal-slope", "get_zonal_slope_statistics", {"admin_name": ref, "max_files": 10}, ["filter-admin"]))
        if "land_use" in tasks:
            steps.append(PlanStep("zonal-land-use", "get_zonal_land_use_distribution", {"admin_name": ref, "max_files": 10}, ["filter-admin"]))
        if "buildability" in parsed.tasks:
            steps.append(PlanStep("buildability-screening", "get_zonal_buildability_analysis", {"admin_name": ref, "max_files": 10, "slope_limit_degrees": float(parsed.constraints.get("slope_max", 15.0))}, ["filter-admin"]))
        return TaskPlan("analyze elevation, derived slope, land-use distribution, and demo buildability screening inside an administrative area", steps, {"type": "terrain_land_use_analysis_result", "summary": True})

    def _build_admin_raster_composite(self, facts: PlanningFacts) -> TaskPlan:
        parsed = facts.spatial
        dataset = "dem" if "elevation" in parsed.tasks else "land_use"
        ref = self._admin_ref()
        steps = self._admin_steps(parsed.admin_name or "")
        steps.append(PlanStep("zonal-raster-statistics", "get_zonal_raster_statistics", {"dataset": dataset, "admin_name": ref, "max_files": 10}, ["filter-admin"]))
        return TaskPlan("resolve administrative area and analyze raster statistics", steps, {"type": "zonal_raster_statistics_result", "summary": True})

    def _build_overview(self, facts: PlanningFacts) -> TaskPlan:
        return self._template_plan(
            "spatial_overview",
            {"admin_name": facts.spatial.admin_name or ""},
            evidence=facts.spatial.evidence,
        )

    def _build_zonal_vector(self, facts: PlanningFacts) -> TaskPlan:
        dataset = "water" if "water" in facts.spatial.tasks else "roads"
        return TaskPlan("summarize OSM vector features inside an administrative area", [PlanStep("zonal-vector", "get_zonal_vector_summary", {"dataset": dataset, "admin_name": facts.spatial.admin_name, "max_features": 10000})], {"type": "zonal_vector_result", "summary": True})

    def _build_vector_relation(self, facts: PlanningFacts) -> TaskPlan:
        match = self._DISTANCE_PATTERN.search(facts.request)
        if match is None:
            raise ClarificationNeeded("missing distance, for example: within 500 meters")
        distance = int(float(match.group(1)))
        return TaskPlan("find water features near roads", [
            PlanStep("schema-roads", "get_dataset_schema", {"dataset": "roads"}),
            PlanStep("schema-water", "get_dataset_schema", {"dataset": "water"}),
            PlanStep("near-water", "spatial_join", {"left_dataset": "roads", "right_dataset": "water", "relation": "near", "distance_m": distance}, ["schema-roads", "schema-water"]),
        ], {"type": "spatial_relation_result", "summary": True})

    def _build_vector_query(self, facts: PlanningFacts) -> TaskPlan:
        dataset = "water" if "water" in facts.spatial.tasks else "roads"
        conditions = []
        if dataset == "roads":
            highway = re.search(r"(motorway|trunk|primary|secondary|tertiary|residential)", facts.request, re.IGNORECASE)
            if highway:
                conditions.append({"field": "highway", "operator": "eq", "value": highway.group(1).lower()})
        return TaskPlan("query OSM {} features".format(dataset), [
            PlanStep("schema-vector", "get_dataset_schema", {"dataset": dataset}),
            PlanStep("filter-vector", "range_query", {"dataset": dataset, "conditions": conditions, "limit": 10000}, ["schema-vector"]),
        ], {"type": "vector_result", "summary": True})

    def _build_zonal_raster(self, facts: PlanningFacts) -> TaskPlan:
        dataset = "dem" if "elevation" in facts.spatial.tasks else "land_use"
        return TaskPlan("analyze raster statistics inside an administrative area", [
            PlanStep("dataset-health", "get_dataset_health_report", {"dataset": dataset, "max_files": 10}),
            PlanStep("zonal-raster-statistics", "get_zonal_raster_statistics", {"dataset": dataset, "admin_name": facts.spatial.admin_name, "max_files": 10}, ["dataset-health"]),
        ], {"type": "zonal_raster_statistics_result", "summary": True})

    def _build_raster_statistics(self, facts: PlanningFacts) -> TaskPlan:
        dataset = "dem" if "elevation" in facts.spatial.tasks else "land_use"
        return TaskPlan("analyze raster value statistics", [PlanStep("raster-statistics", "get_raster_statistics", {"dataset": dataset, "max_files": 3})], {"type": "raster_statistics_result", "summary": True})

    def _build_raster_metadata(self, facts: PlanningFacts) -> TaskPlan:
        return self._template_plan(
            "raster_metadata",
            {"dataset": self._raster_dataset(facts.spatial)},
            evidence=facts.spatial.evidence,
        )

    def _build_admin_boundary(self, facts: PlanningFacts) -> TaskPlan:
        if not facts.spatial.admin_name:
            raise ClarificationNeeded("missing admin area name, for example: 洪山区")
        return self._template_plan(
            "admin_boundary_query",
            {"admin_name": facts.spatial.admin_name},
            evidence=facts.spatial.evidence,
        )

    def _build_legacy_road_slope(self, facts: PlanningFacts) -> TaskPlan:
        slope = int(float(self._SLOPE_PATTERN.search(facts.request).group(1)))
        distance = self._DISTANCE_PATTERN.search(facts.request)
        if distance is None:
            raise ClarificationNeeded("missing road distance, for example: within 500 meters of roads")
        return TaskPlan("identify high-slope spatial areas near roads", [
            PlanStep("schema-roads", "get_dataset_schema", {"dataset": "roads"}),
            PlanStep("schema-slope", "get_dataset_schema", {"dataset": "slope"}),
            PlanStep("filter-slope", "range_query", {"dataset": "slope", "conditions": [{"field": "slope_degree", "operator": "gt", "value": slope}], "limit": 10000}, ["schema-slope"]),
            PlanStep("near-roads", "spatial_join", {"left_dataset": "roads", "right_dataset": "slope", "relation": "near", "distance_m": int(float(distance.group(1)))}, ["schema-roads", "filter-slope"]),
        ], {"type": "spatial_result", "summary": True})

    def _clarify_unmatched(self, facts: PlanningFacts) -> None:
        intent = classify_spatial_intent(facts.request)
        if self._has(facts.request, ("坡度", "高坡度")) and not self._SLOPE_PATTERN.search(facts.request):
            raise ClarificationNeeded("missing slope threshold, for example: slope greater than 25 degrees")
        if intent["is_spatial"]:
            raise ClarificationNeeded(clarification_message(facts.request), clarification_details(facts.request))
        raise ClarificationNeeded("M1 requires a road condition and an explicit slope threshold")
