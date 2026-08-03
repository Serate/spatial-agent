import json
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol

from .errors import ToolError


class ToolAdapter(Protocol):
    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class ToolRegistry:
    """A deep module that validates and dispatches all tool calls."""

    def __init__(self, definitions: Mapping[str, Mapping[str, Any]], adapter: ToolAdapter):
        self._definitions = dict(definitions)
        self._adapter = adapter

    @classmethod
    def from_json(cls, path: str, adapter: ToolAdapter) -> "ToolRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = {tool["name"]: tool for tool in payload["tools"]}
        return cls(definitions, adapter)

    @property
    def names(self):
        return tuple(self._definitions.keys())

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        definition = self._definitions.get(name)
        if definition is None:
            raise ToolError("Unknown tool: " + name)
        schema = definition.get("input_schema", {})
        self._validate(arguments, schema, "$")
        try:
            result = self._adapter.invoke(name, arguments)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError("Tool execution failed: " + str(exc)) from exc
        if not isinstance(result, dict):
            raise ToolError("Tool must return an object: " + name)
        return result

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


class DemoSpatialAdapter:
    """Deterministic Adapter used by M1 before real spatial data is connected."""

    _schemas = {
        "roads": {
            "geometry_type": "LineString",
            "crs": "EPSG:4326",
            "fields": ["id", "road_level", "geometry"],
        },
        "slope": {
            "geometry_type": "Polygon",
            "crs": "EPSG:4326",
            "fields": ["id", "slope_degree", "geometry"],
        },
        "admin_areas": {
            "geometry_type": "Polygon",
            "crs": "EPSG:4326",
            "fields": ["id", "name", "geometry"],
        },
    }

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "get_dataset_schema":
            dataset = arguments["dataset"]
            return {"dataset": dataset, **self._schemas[dataset]}
        if name == "range_query":
            return {
                "result_ref": "demo://range/" + arguments["dataset"],
                "count": 12,
                "crs": "EPSG:4326",
            }
        if name == "spatial_join":
            if arguments["relation"] == "near" and "distance_m" not in arguments:
                raise ToolError("near relation requires distance_m")
            return {
                "result_ref": "demo://join/"
                + arguments["left_dataset"]
                + "-"
                + arguments["right_dataset"],
                "count": 7,
                "left_dataset": arguments["left_dataset"],
                "right_dataset": arguments["right_dataset"],
            }
        raise ToolError("Adapter does not implement: " + name)
