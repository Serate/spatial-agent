import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol

from .errors import ToolError
from .spatial_backend import InMemorySpatialBackend, SpatialToolAdapter

_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolAdapter(Protocol):
    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class ToolRegistry:
    """A deep module that validates and dispatches all tool calls."""

    def __init__(self, definitions: Mapping[str, Mapping[str, Any]], adapter: ToolAdapter):
        self._definitions = dict(definitions)
        self._adapter = adapter
        self._dynamic_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    @classmethod
    def from_json(cls, path: str, adapter: ToolAdapter) -> "ToolRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = {tool["name"]: tool for tool in payload["tools"]}
        return cls(definitions, adapter)

    @property
    def names(self):
        return tuple(self._definitions.keys())

    def register_tool(
        self,
        name: str,
        definition: Mapping[str, Any],
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Register one dynamic tool (M81.2).

        Validation keeps the boundary controlled: the name must be a fresh
        identifier, the definition must carry an object input_schema, and the
        handler must be callable and return a dict. Registered tools still go
        through ``invoke`` -> ``_validate`` like any static tool.
        """
        if not isinstance(name, str) or not _TOOL_NAME_RE.match(name):
            raise ToolError("dynamic tool name must be a lowercase identifier")
        if name in self._definitions:
            raise ToolError("tool already registered: " + name)
        if not isinstance(definition, Mapping) or not isinstance(
            definition.get("input_schema"), Mapping
        ):
            raise ToolError("dynamic tool definition must include an input_schema")
        if definition.get("input_schema", {}).get("type") != "object":
            raise ToolError("dynamic tool input_schema must be an object schema")
        if not callable(handler):
            raise ToolError("dynamic tool handler must be callable")
        entry = dict(definition)
        entry["name"] = name
        entry["dynamic"] = True
        self._definitions[name] = entry
        self._dynamic_handlers[name] = handler
        return {
            "name": name,
            "dynamic": True,
            "description": str(definition.get("description") or ""),
            "input_schema": definition["input_schema"],
        }

    def dynamic_tools(self) -> list:
        """Return bounded summaries of the dynamically registered tools."""
        return [
            {
                "name": name,
                "description": str(
                    (self._definitions.get(name) or {}).get("description") or ""
                ),
            }
            for name in sorted(self._dynamic_handlers)
        ]

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        definition = self._definitions.get(name)
        if definition is None:
            raise ToolError("Unknown tool: " + name)
        schema = definition.get("input_schema", {})
        self._validate(arguments, schema, "$")
        handler = self._dynamic_handlers.get(name)
        if handler is not None:
            try:
                result = handler(arguments)
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError("Tool execution failed: " + str(exc)) from exc
            if not isinstance(result, dict):
                raise ToolError("Tool must return an object: " + name)
            return result
        try:
            result = self._adapter.invoke(name, arguments)
        except ToolError as exc:
            if "does not implement" in str(exc) and name in self._definitions:
                # A static definition without an adapter implementation is a
                # configuration error, not a dynamic tool.
                raise
            raise
        except Exception as exc:
            raise ToolError("Tool execution failed: " + str(exc)) from exc
        if not isinstance(result, dict):
            raise ToolError("Tool must return an object: " + name)
        return result

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        exporter = getattr(self._adapter, "export_result", None)
        if not callable(exporter):
            raise ToolError("adapter does not support result export")
        return exporter(result_ref, max_features=max_features)

    def _validate(self, value: Any, schema: Mapping[str, Any], path: str) -> None:
        expected = schema.get("type")
        if expected == "object":
            if not isinstance(value, dict):
                raise ToolError(path + " must be an object")
            required = schema.get("required", [])
            missing = [key for key in required if key not in value]
            if missing:
                raise ToolError(path + " missing required fields: " + ", ".join(missing))
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                extra = [key for key in value if key not in properties]
                if extra:
                    raise ToolError(path + " has unknown fields: " + ", ".join(extra))
            for key, item in value.items():
                if key in properties:
                    self._validate(item, properties[key], path + "." + key)
        elif expected == "array":
            if not isinstance(value, list):
                raise ToolError(path + " must be an array")
            if "minItems" in schema and len(value) < schema["minItems"]:
                raise ToolError(path + " has too few items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                raise ToolError(path + " has too many items")
            item_schema = schema.get("items")
            if item_schema:
                for index, item in enumerate(value):
                    self._validate(item, item_schema, path + "[" + str(index) + "]")
        elif expected == "string" and not isinstance(value, str):
            raise ToolError(path + " must be a string")
        elif expected == "number" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            raise ToolError(path + " must be a number")
        elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ToolError(path + " must be an integer")

        if "enum" in schema and value not in schema["enum"]:
            raise ToolError(path + " must be one of: " + ", ".join(map(str, schema["enum"])))
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolError(path + " is below the minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolError(path + " is above the maximum")


class DemoSpatialAdapter(SpatialToolAdapter):
    """Backward-compatible name for the M1 demo adapter."""

    def __init__(self):
        super().__init__(InMemorySpatialBackend())
