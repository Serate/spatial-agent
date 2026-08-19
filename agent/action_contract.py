"""Bounded input validation for Domain-owned actions."""

from __future__ import annotations

from typing import Any, Mapping


class ActionContractError(ValueError):
    """A bounded, machine-identifiable action contract failure."""

    def __init__(self, message: str, *, action_id: str, code: str = "action_invalid_input"):
        super().__init__(message)
        self.action_id = str(action_id)[:96]
        self.code = str(code)[:96]


def validate_action_payload(
    value: Any,
    schema: Mapping[str, Any] | None,
    *,
    path: str = "$",
) -> None:
    """Validate the small JSON-schema subset used by declared actions.

    The validator deliberately mirrors the ToolRegistry's bounded contract:
    it validates shape, required fields, additional properties, scalar bounds,
    and nested array items without accepting arbitrary schema execution.
    """
    if not isinstance(schema, Mapping):
        return
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, Mapping):
            raise ValueError(path + " must be an object")
        properties = schema.get("properties")
        properties = properties if isinstance(properties, Mapping) else {}
        required = schema.get("required") or []
        missing = [str(key) for key in required if key not in value]
        if missing:
            raise ValueError(path + " missing required fields: " + ", ".join(missing))
        if schema.get("additionalProperties") is False:
            extra = [str(key) for key in value if key not in properties]
            if extra:
                raise ValueError(path + " has unknown fields: " + ", ".join(extra))
        for key, item in value.items():
            if key in properties:
                validate_action_payload(item, properties[key], path=path + "." + str(key))
        return
    if expected == "array":
        if not isinstance(value, list):
            raise ValueError(path + " must be an array")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValueError(path + " has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(path + " has too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                validate_action_payload(item, item_schema, path=f"{path}[{index}]")
        return
    if expected == "string":
        if not isinstance(value, str):
            raise ValueError(path + " must be a string")
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(path + " is shorter than the minimum length")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(path + " is longer than the maximum length")
        return
    if expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(path + " must be a number")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(path + " is below the minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(path + " is above the maximum")
        return
    if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(path + " must be an integer")
    if expected == "boolean" and not isinstance(value, bool):
        raise ValueError(path + " must be a boolean")


__all__ = ["ActionContractError", "validate_action_payload"]
