"""Domain-neutral validation for bounded Composite input references.

Components may depend on another component's public result, but the reference
must be explicit, ordered, and type-compatible with the producer declaration.
This module only validates metadata; it never reads a result or dispatches a
tool.  Execution remains owned by the existing Composite coordinator and
Domain Runtime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent.data_kinds import SUPPORTED_DATA_KINDS


COMPOSITION_SCHEMA_VERSION = "spatial-agent.composition.v1"
_MAX_INPUTS = 8
_MAX_TEXT = 160
_ALLOWED_INPUT_FIELDS = {"name", "source", "accepted_kinds", "required"}
_ALLOWED_SOURCE_FIELDS = {"component_id", "path"}


class CompositionError(ValueError):
    """A component input reference cannot cross the composition boundary."""

    def __init__(self, message: str, *, code: str = "composition_invalid") -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def normalize_component_inputs(value: Any) -> list[dict[str, Any]]:
    """Normalize the public component-to-component input reference list."""

    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_INPUTS:
        raise CompositionError(
            "component inputs must be a bounded array", code="composition_inputs_invalid"
        )
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) - _ALLOWED_INPUT_FIELDS:
            raise CompositionError(
                "component input contains unsupported fields",
                code="composition_input_field_invalid",
            )
        name = _text(raw.get("name"), _MAX_TEXT)
        if not name or name in names:
            raise CompositionError(
                "component input names must be unique and non-empty",
                code="composition_input_name_invalid",
            )
        source = raw.get("source")
        if not isinstance(source, Mapping) or set(source) - _ALLOWED_SOURCE_FIELDS:
            raise CompositionError(
                "component input source is invalid",
                code="composition_input_source_invalid",
            )
        component_id = _text(source.get("component_id"), 48)
        path = _text(source.get("path"), _MAX_TEXT)
        if not component_id or not path or path.split(".")[0] != "result":
            raise CompositionError(
                "component input source must point to a public result path",
                code="composition_input_source_invalid",
            )
        if any(not part.strip() for part in path.split(".")):
            raise CompositionError(
                "component input source path is invalid",
                code="composition_input_source_invalid",
            )
        kinds = _kinds(raw.get("accepted_kinds"))
        if not kinds:
            raise CompositionError(
                "component input accepted_kinds is required",
                code="composition_input_types_missing",
            )
        names.add(name)
        result.append(
            {
                "name": name,
                "source": {"component_id": component_id, "path": path},
                "accepted_kinds": kinds,
                "required": bool(raw.get("required", True)),
            }
        )
    return result


def validate_component_composition(
    components: Sequence[Mapping[str, Any]],
    *,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Validate dependencies and optional producer/consumer data profiles."""

    if not isinstance(components, (list, tuple)):
        raise CompositionError("components must be a sequence")
    positions = {
        str(item.get("component_id")): index
        for index, item in enumerate(components)
        if isinstance(item, Mapping) and item.get("component_id")
    }
    if len(positions) != len(components):
        raise CompositionError(
            "component ids must be unique and non-empty",
            code="composition_component_identity_invalid",
        )
    for index, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise CompositionError("component must be an object", code="composition_component_invalid")
        component_id = _text(component.get("component_id"), 48)
        dependencies = component.get("depends_on") or []
        if not isinstance(dependencies, list):
            raise CompositionError("component dependencies are invalid", code="composition_dependencies_invalid")
        for item in normalize_component_inputs(component.get("inputs")):
            source_id = item["source"]["component_id"]
            if source_id not in positions:
                raise CompositionError(
                    "component input source does not exist",
                    code="composition_input_source_missing",
                )
            if source_id not in dependencies:
                raise CompositionError(
                    "component input source must be declared as a dependency",
                    code="composition_input_dependency_missing",
                )
            if positions[source_id] >= index:
                raise CompositionError(
                    "component input source must run earlier",
                    code="composition_input_order_invalid",
                )
            producer_kinds = _producer_kinds(components, source_id, context)
            if producer_kinds and not producer_kinds.intersection(item["accepted_kinds"]):
                raise CompositionError(
                    "component input data profile is incompatible with its source",
                    code="composition_input_type_mismatch",
                )


def project_component_inputs(value: Any) -> list[dict[str, Any]]:
    """Return a bounded safe projection for plans, evidence, and recovery."""

    try:
        return normalize_component_inputs(value)
    except CompositionError:
        return []


def _producer_kinds(
    components: Sequence[Mapping[str, Any]],
    component_id: str,
    context: Mapping[str, Any] | None,
) -> set[str]:
    source = next(
        (item for item in components if isinstance(item, Mapping) and str(item.get("component_id")) == component_id),
        None,
    )
    if not isinstance(source, Mapping) or not isinstance(context, Mapping):
        return set()
    domain_id = str(source.get("domain_id") or "")
    capability_id = str(source.get("capability_id") or "")
    for item in context.get("capability_index") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("domain_id")) != domain_id or str(item.get("capability_id")) != capability_id:
            continue
        kinds: set[str] = set()
        for profile in item.get("output_profiles") or []:
            if isinstance(profile, Mapping):
                kinds.update(_kinds(profile.get("kinds")))
        return kinds
    return set()


def _kinds(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in list(values)[:8]:
        kind = str(item or "").strip()
        if kind not in SUPPORTED_DATA_KINDS:
            raise CompositionError("unsupported component input data kind", code="composition_input_type_invalid")
        if kind not in result:
            result.append(kind)
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "COMPOSITION_SCHEMA_VERSION",
    "CompositionError",
    "normalize_component_inputs",
    "project_component_inputs",
    "validate_component_composition",
]
