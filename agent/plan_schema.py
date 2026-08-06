from typing import Any, Dict, Iterable, List, Mapping

from .errors import PlanningError
from .models import PlanStep, TaskPlan


TASK_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["goal", "steps"],
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string"},
        "outcome": {"type": "string", "enum": ["success", "direct_answer", "needs_clarification", "rejected"]},
        "message": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "output": {"type": "object"},
        "steps": {
            "type": "array",
            "minItems": 0,
            "items": {
                "type": "object",
                "required": ["id", "tool", "args"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def task_plan_schema() -> Dict[str, Any]:
    return TASK_PLAN_SCHEMA


def parse_task_plan(payload: Mapping[str, Any], allowed_tools: Iterable[str]) -> TaskPlan:
    if not isinstance(payload, Mapping):
        raise PlanningError("planner output must be an object")

    allowed = set(allowed_tools)
    goal = _required_string(payload, "goal")
    steps_payload = payload.get("steps")
    if not isinstance(steps_payload, list):
        raise PlanningError("planner output must include a steps array")

    steps: List[PlanStep] = []
    seen_ids = set()
    for index, item in enumerate(steps_payload):
        if not isinstance(item, Mapping):
            raise PlanningError("step {} must be an object".format(index))
        step_id = _required_string(item, "id")
        if step_id in seen_ids:
            raise PlanningError("duplicate step id: " + step_id)
        seen_ids.add(step_id)
        tool = _required_string(item, "tool")
        if tool not in allowed:
            raise PlanningError("planner selected an unknown tool: " + tool)
        args = item.get("args")
        if not isinstance(args, dict):
            raise PlanningError("step args must be an object: " + step_id)
        depends_on = item.get("depends_on", [])
        if not isinstance(depends_on, list) or not all(isinstance(dep, str) for dep in depends_on):
            raise PlanningError("depends_on must be an array of strings: " + step_id)
        steps.append(PlanStep(step_id, tool, args, depends_on))

    step_positions = {step.id: index for index, step in enumerate(steps)}
    for index, step in enumerate(steps):
        for source_id, path in _find_result_references(step.args):
            if source_id not in step_positions:
                raise PlanningError(
                    "result reference points to unknown step: " + source_id
                )
            if source_id == step.id:
                raise PlanningError("step cannot reference its own result: " + step.id)
            if source_id not in step.depends_on:
                raise PlanningError(
                    "result reference must be listed in depends_on: " + step.id
                )
            if step_positions[source_id] >= index:
                raise PlanningError(
                    "result reference step must run earlier: " + source_id
                )

    output = payload.get("output", {})
    if not isinstance(output, dict):
        raise PlanningError("output must be an object")

    assumptions = payload.get("assumptions", [])
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        raise PlanningError("assumptions must be an array of strings")

    if not steps and output.get("type") != "direct_answer":
        raise PlanningError("planner output must include at least one step")
    if output.get("type") == "direct_answer":
        if steps:
            raise PlanningError("direct_answer must not include tool steps")
        message = payload.get("message") or output.get("message")
        if not isinstance(message, str) or not message.strip():
            raise PlanningError("direct_answer requires a non-empty message")
        output = {**output, "message": message}

    return TaskPlan(goal=goal, steps=steps, output=output, assumptions=assumptions)


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PlanningError(key + " must be a non-empty string")
    return value


def _find_result_references(value: Any) -> List[Any]:
    references = []
    if isinstance(value, dict):
        if "$from" in value or "path" in value:
            if set(value) != {"$from", "path"}:
                raise PlanningError("result reference must contain only $from and path")
            source = value["$from"]
            path = value["path"]
            if not isinstance(source, str) or not source.strip():
                raise PlanningError("result reference $from must be a non-empty string")
            if not isinstance(path, str) or not path.strip():
                raise PlanningError("result reference path must be a non-empty string")
            if any(not part.strip() for part in path.split(".")):
                raise PlanningError("result reference path contains an empty segment")
            references.append((source, path))
        else:
            for item in value.values():
                references.extend(_find_result_references(item))
    elif isinstance(value, list):
        for item in value:
            references.extend(_find_result_references(item))
    return references
