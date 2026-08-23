"""Pluggable sources of tool definitions and implementations.

The runtime keeps validation and dispatch policy in ``ToolRegistry``. A
provider only supplies a bounded definition catalogue and performs the
provider-specific invocation. This is the seam for native tools today and
MCP/HTTP providers later; it is deliberately not an MCP dependency.
"""

import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol

from .errors import ToolError


TOOL_PROVIDER_HEALTH_SCHEMA = "spatial-agent.tool-provider-health.v1"
TOOL_PROVIDER_CONTRACT_SCHEMA = "spatial-agent.tool-provider-contract.v1"
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class NativeToolAdapter(Protocol):
    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class ToolProvider(Protocol):
    """Small provider interface consumed by the ToolRegistry."""

    @property
    def provider_id(self) -> str:
        ...

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        ...

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class ToolProviderError(ToolError):
    """Safe, classified failure raised by an external tool provider."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "unknown",
        code: str = "provider_error",
        retryable: bool = False,
    ):
        self.provider_id = str(provider_id)[:64]
        super().__init__(
            message,
            category="provider",
            code=code,
            retryable=retryable,
        )


def validate_tool_definitions(
    definitions: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Validate and snapshot the provider definition catalogue.

    Provider implementations are replaceable, but their tool catalogue is
    not allowed to weaken the Registry seam.  This deliberately validates the
    small subset of JSON Schema and governance metadata that the Runtime
    consumes.  It is not a second schema engine: invocation still performs
    the complete argument validation in ``ToolRegistry``.
    """
    if not isinstance(definitions, Mapping):
        raise ToolError("tool provider definitions must be an object")

    validated: Dict[str, Dict[str, Any]] = {}
    for name, raw_definition in definitions.items():
        if not isinstance(name, str) or not _TOOL_NAME_RE.match(name):
            raise ToolError("tool provider definition has an invalid name")
        if not isinstance(raw_definition, Mapping):
            raise ToolError("tool definition must be an object: " + name)

        definition = deepcopy(dict(raw_definition))
        declared_name = definition.get("name")
        if declared_name is not None and declared_name != name:
            raise ToolError("tool definition name does not match catalogue key: " + name)
        # Providers may use the catalogue key as the canonical name.  The
        # Registry and planner should see one stable representation.
        definition["name"] = name

        _validate_schema_object(definition.get("input_schema"), name, "input_schema")
        if "output_schema" in definition and definition["output_schema"] is not None:
            _validate_schema_object(definition["output_schema"], name, "output_schema")
        _validate_string_list(definition, "permissions", name)
        _validate_string_list(definition, "data_dependencies", name)
        _validate_string_list(definition, "required_datasets", name)

        if "requires_approval" in definition and not isinstance(
            definition["requires_approval"], bool
        ):
            raise ToolError("tool requires_approval must be boolean: " + name)
        if "side_effect" in definition and not isinstance(definition["side_effect"], str):
            raise ToolError("tool side_effect must be a string: " + name)
        if "timeout_seconds" in definition:
            timeout = definition["timeout_seconds"]
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(float(timeout))
                or float(timeout) <= 0
            ):
                raise ToolError("tool timeout_seconds must be positive: " + name)
        validated[name] = definition
    return validated


def _validate_schema_object(value: Any, tool_name: str, field_name: str) -> None:
    if not isinstance(value, Mapping) or value.get("type") != "object":
        raise ToolError(
            "tool " + tool_name + " " + field_name + " must be an object schema"
        )
    properties = value.get("properties", {})
    if properties is not None and not isinstance(properties, Mapping):
        raise ToolError(
            "tool " + tool_name + " " + field_name + ".properties must be an object"
        )
    required = value.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ToolError(
            "tool " + tool_name + " " + field_name + ".required must be a string list"
        )
    additional = value.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        raise ToolError(
            "tool " + tool_name + " " + field_name
            + ".additionalProperties must be boolean"
        )


def _validate_string_list(
    definition: Mapping[str, Any], field_name: str, tool_name: str
) -> None:
    if field_name not in definition or definition[field_name] is None:
        return
    value = definition[field_name]
    if isinstance(value, str):
        return
    if not isinstance(value, (list, tuple, set)) or not all(
        isinstance(item, str) for item in value
    ):
        raise ToolError("tool " + tool_name + " " + field_name + " must be a string list")


class NativeToolProvider:
    """Provider for in-process adapters and repository tool definitions."""

    def __init__(self, definitions: Mapping[str, Mapping[str, Any]], adapter: NativeToolAdapter):
        self._definitions = deepcopy(dict(definitions))
        self._adapter = adapter

    @property
    def provider_id(self) -> str:
        return "native"

    def health(self) -> Dict[str, Any]:
        return {
            "schema_version": TOOL_PROVIDER_HEALTH_SCHEMA,
            "status": "ready",
            "checks": [
                {"name": "definitions", "status": "passed"},
                {"name": "adapter", "status": "passed"},
            ],
        }

    @classmethod
    def from_json(cls, path: str, adapter: NativeToolAdapter) -> "NativeToolProvider":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = {tool["name"]: tool for tool in payload["tools"]}
        return cls(definitions, adapter)

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        """Return a copy so a Registry cannot mutate provider state."""
        return deepcopy(self._definitions)

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._adapter.invoke(name, arguments)

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        exporter = getattr(self._adapter, "export_result", None)
        if not callable(exporter):
            raise AttributeError("native adapter does not support result export")
        return exporter(result_ref, max_features=max_features)


class UnavailableToolProvider:
    """Definition-compatible adapter for a provider that failed to initialize.

    Keeping the catalogue available lets capability discovery, planning, and
    ToolRegistry validation run normally.  Invocation then enters the shared
    Runtime failure lifecycle instead of leaking a startup exception past the
    request boundary.
    """

    def __init__(
        self,
        definitions: Mapping[str, Mapping[str, Any]],
        *,
        provider_id: str = "unavailable",
        reason_code: str = "provider_initialization_unavailable",
        message: str = "tool provider is unavailable; verify its runtime configuration",
    ) -> None:
        self._definitions = deepcopy(dict(definitions))
        self._provider_id = str(provider_id or "unavailable")[:64]
        self._reason_code = str(reason_code or "provider_initialization_unavailable")[:96]
        self._message = str(message or "tool provider is unavailable")[:240]

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @classmethod
    def from_json(
        cls,
        path: str,
        **kwargs: Any,
    ) -> "UnavailableToolProvider":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = {tool["name"]: tool for tool in payload["tools"]}
        return cls(definitions, **kwargs)

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        return deepcopy(self._definitions)

    def health(self) -> Dict[str, Any]:
        return {
            "schema_version": TOOL_PROVIDER_HEALTH_SCHEMA,
            "status": "unavailable",
            "reason_code": self._reason_code,
            "checks": [
                {"name": "definitions", "status": "passed"},
                {"name": "adapter", "status": "failed"},
            ],
        }

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raise ToolProviderError(
            self._message,
            provider_id=self._provider_id,
            code=self._reason_code,
            # Configuration or mounted data can be restored without changing
            # the request, so expose the standard retry/recover interaction.
            retryable=True,
        )

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        return self.invoke("export_result", {"result_ref": result_ref})
