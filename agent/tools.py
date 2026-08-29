import re
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable, Dict, Iterable, Mapping, Protocol

from .errors import ToolError
from .tool_provider import (
    TOOL_PROVIDER_CONTRACT_SCHEMA,
    NativeToolProvider,
    ToolProvider,
    ToolProviderError,
    validate_tool_definitions,
)

_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolAdapter(Protocol):
    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class ToolRegistry:
    """A deep module that validates and dispatches all tool calls."""

    def __init__(
        self,
        definitions: Mapping[str, Mapping[str, Any]] | None = None,
        adapter: ToolAdapter | None = None,
        *,
        provider: ToolProvider | None = None,
    ):
        if provider is None:
            if definitions is None or adapter is None:
                raise TypeError("ToolRegistry requires definitions and adapter, or a provider")
            provider = NativeToolProvider(definitions, adapter)
        elif definitions is not None or adapter is not None:
            raise TypeError("provide either provider or definitions/adapter, not both")
        self._provider = provider
        provider_definitions = provider.definitions()
        self._definitions = validate_tool_definitions(provider_definitions)
        self._dynamic_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._approval_bindings: Dict[str, str] = {}
        self._approval_guard: Callable[[Mapping[str, Any]], None] | None = None

    @classmethod
    def from_json(cls, path: str, adapter: ToolAdapter) -> "ToolRegistry":
        return cls(provider=NativeToolProvider.from_json(path, adapter))

    @classmethod
    def from_provider(cls, provider: ToolProvider) -> "ToolRegistry":
        """Build a Registry from any provider without exposing its adapter."""
        return cls(provider=provider)

    def set_approval_guard(
        self, guard: Callable[[Mapping[str, Any]], None] | None
    ) -> None:
        """Install the Runtime-owned approval check for dynamic dispatch."""
        if guard is not None and not callable(guard):
            raise TypeError("approval guard must be callable")
        self._approval_guard = guard

    @property
    def names(self):
        return tuple(self._definitions.keys())

    def provider_info(self) -> Dict[str, Any]:
        """Return safe provider identity for capability and plan evidence."""
        return {
            "id": str(getattr(self._provider, "provider_id", "unknown"))[:64],
            "tool_count": len(self._definitions),
        }

    def provider_contract(self) -> Dict[str, Any]:
        """Return the validated provider/catalog contract evidence."""
        return {
            "schema_version": TOOL_PROVIDER_CONTRACT_SCHEMA,
            "provider_id": self.provider_info()["id"],
            "status": "valid",
            "tool_count": len(self._definitions),
            "validation": "registry_definition_schema",
        }

    def provider_health(self) -> Dict[str, Any]:
        """Return bounded provider health without invoking a business tool."""
        info = self.provider_info()
        checker = getattr(self._provider, "health", None)
        if not callable(checker):
            return {
            "schema_version": "spatial-agent.tool-provider-health.v1",
            "provider_id": info["id"],
            "status": "unknown",
            "tool_count": info["tool_count"],
            "definition_contract": self.provider_contract(),
            "reason_code": "health_check_not_supported",
            }
        try:
            raw = checker()
        except Exception:
            return {
                "schema_version": "spatial-agent.tool-provider-health.v1",
                "provider_id": info["id"],
                "status": "unavailable",
                "tool_count": info["tool_count"],
                "definition_contract": self.provider_contract(),
                "reason_code": "health_check_failed",
            }
        if not isinstance(raw, Mapping):
            raw = {}
        status = str(raw.get("status", "unknown"))
        if status not in {"ready", "degraded", "unavailable", "unknown"}:
            status = "unknown"
        checks = []
        for item in raw.get("checks") or []:
            if not isinstance(item, Mapping):
                continue
            check_status = str(item.get("status", "unknown"))
            if check_status not in {"passed", "warning", "failed", "unknown"}:
                check_status = "unknown"
            checks.append({
                "name": str(item.get("name", "check"))[:64],
                "status": check_status,
            })
        return {
            "schema_version": "spatial-agent.tool-provider-health.v1",
            "provider_id": info["id"],
            "status": status,
            "tool_count": info["tool_count"],
            "definition_contract": self.provider_contract(),
            "checks": checks[:12],
            "reason_code": str(raw.get("reason_code"))[:96]
            if raw.get("reason_code")
            else None,
        }

    def governance_summary(self, *, max_tools: int = 32) -> Dict[str, Any]:
        """Expose bounded permissions and data-dependency metadata."""
        tools = []
        approval_count = 0
        side_effect_count = 0
        for name in sorted(self._definitions):
            if len(tools) >= max(1, min(int(max_tools), 64)):
                break
            definition = self._definitions.get(name)
            if not isinstance(definition, Mapping):
                continue
            item = _tool_governance_summary(name, definition)
            approval_count += int(item["requires_approval"])
            side_effect_count += int(item["side_effect"] not in {"none", "unknown"})
            tools.append(item)
        return {
            "schema_version": "spatial-agent.tool-governance.v1",
            "provider_id": self.provider_info()["id"],
            "tool_count": len(self._definitions),
            "returned_tool_count": len(tools),
            "requires_approval_count": approval_count,
            "side_effect_tool_count": side_effect_count,
            "tools": tools,
        }

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

    def register_approved_tool(
        self,
        approval: Mapping[str, Any],
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Publish one approved proposal through the Registry boundary.

        Approval records are public projections, so the method accepts only
        their bounded definition and fingerprint.  Source loading and source
        execution remain outside the Registry and must be represented by the
        injected controlled handler.
        """
        if not isinstance(approval, Mapping):
            raise ToolError(
                "tool approval must be an object",
                category="policy",
                code="approval_record_invalid",
                retryable=False,
            )
        if approval.get("status") != "approved":
            raise ToolError(
                "only an approved tool proposal can enter the Registry",
                category="policy",
                code="approval_required",
                retryable=False,
            )
        approval_id = str(approval.get("approval_id") or "").strip()
        fingerprint = str(approval.get("receipt_fingerprint") or "").strip()
        name = str(approval.get("name") or "").strip()
        definition = approval.get("definition")
        if not approval_id or not fingerprint or not name or not isinstance(definition, Mapping):
            raise ToolError(
                "approved tool definition is incomplete",
                category="validation",
                code="approval_definition_missing",
                retryable=False,
            )
        if str(definition.get("name") or "").strip() != name:
            raise ToolError(
                "approved tool definition identity does not match approval",
                category="validation",
                code="approval_definition_mismatch",
                retryable=False,
            )
        if not callable(handler):
            raise ToolError(
                "approved tool handler must be callable",
                category="validation",
                code="approval_handler_invalid",
                retryable=False,
            )
        existing = self._definitions.get(name)
        if existing is not None:
            if str(existing.get("approval_id") or "") == approval_id:
                if (
                    int(existing.get("approval_version") or 0)
                    != int(approval.get("version") or 0)
                    or str(existing.get("approval_fingerprint") or "") != fingerprint
                ):
                    raise ToolError(
                        "approved tool binding is stale",
                        category="policy",
                        code="approval_binding_stale",
                        retryable=False,
                    )
                return self._registered_tool_summary(name, existing)
            raise ToolError("tool already registered: " + name)
        entry = dict(definition)
        entry.update(
            {
                "name": name,
                "dynamic": True,
                "requires_approval": False,
                "approval_id": approval_id,
                "approval_version": int(approval.get("version") or 0),
                "approval_fingerprint": fingerprint,
                "handler_ref": "approval:" + approval_id,
            }
        )
        registered = self.register_tool(name, entry, handler)
        self._approval_bindings[approval_id] = name
        registered.update(
            {
                "approval_id": approval_id,
                "approval_version": entry["approval_version"],
                "approval_fingerprint": fingerprint,
                "handler_ref": entry["handler_ref"],
            }
        )
        return registered

    def revoke_approved_tool(self, approval_id: str) -> bool:
        """Remove a previously published proposal from this Registry."""
        key = str(approval_id or "").strip()
        name = self._approval_bindings.pop(key, None)
        if not name:
            return False
        definition = self._definitions.get(name)
        if isinstance(definition, Mapping) and definition.get("approval_id") == key:
            self._definitions.pop(name, None)
            self._dynamic_handlers.pop(name, None)
            return True
        return False

    def _registered_tool_summary(self, name: str, definition: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "name": name,
            "dynamic": bool(definition.get("dynamic", False)),
            "description": str(definition.get("description") or ""),
            "input_schema": definition.get("input_schema") or {"type": "object"},
            **{
                key: definition[key]
                for key in ("approval_id", "approval_version", "approval_fingerprint", "handler_ref")
                if key in definition
            },
        }

    def dynamic_tools(self) -> list:
        """Return bounded summaries of the dynamically registered tools."""
        return [
            {
                "name": name,
                "description": str(
                    (self._definitions.get(name) or {}).get("description") or ""
                ),
                **{
                    key: (self._definitions.get(name) or {}).get(key)
                    for key in (
                        "approval_id",
                        "approval_version",
                        "approval_fingerprint",
                        "handler_ref",
                    )
                    if key in (self._definitions.get(name) or {})
                },
            }
            for name in sorted(self._dynamic_handlers)
        ]

    def definition_summary(
        self,
        tool_names: Iterable[str] | None = None,
        *,
        max_tools: int = 32,
    ) -> Dict[str, Dict[str, Any]]:
        """Return bounded, read-only tool definition summaries for planning context."""
        names = list(tool_names) if tool_names is not None else sorted(self._definitions)
        summary: Dict[str, Dict[str, Any]] = {}
        for name in names:
            if len(summary) >= max_tools:
                break
            definition = self._definitions.get(name)
            if not isinstance(definition, Mapping):
                continue
            input_schema = definition.get("input_schema")
            output_schema = definition.get("output_schema")
            properties = (
                input_schema.get("properties", {})
                if isinstance(input_schema, Mapping)
                else {}
            )
            summary[name] = {
                "description": str(definition.get("description") or "")[:180],
                "side_effect": str(definition.get("side_effect") or "unknown")[:32],
                "requires_approval": bool(definition.get("requires_approval", False)),
                "dynamic": bool(definition.get("dynamic", False)),
                "input_schema": {
                    "required": list(input_schema.get("required", []))
                    if isinstance(input_schema, Mapping)
                    else [],
                    "properties": {
                        str(key): _schema_property_summary(value)
                        for key, value in properties.items()
                        if isinstance(value, Mapping)
                    } if isinstance(properties, Mapping) else {},
                    "additionalProperties": input_schema.get("additionalProperties", True)
                    if isinstance(input_schema, Mapping)
                    else True,
                },
                "output_schema": {
                    "required": list(output_schema.get("required", []))
                    if isinstance(output_schema, Mapping)
                    else [],
                },
            }
            summary[name].update(_tool_governance_summary(name, definition))
        return summary

    def governance_for(self, name: str) -> Dict[str, Any]:
        """Return the bounded governance contract for one registered tool."""
        definition = self._definitions.get(name)
        if not isinstance(definition, Mapping):
            raise ToolError("Unknown tool: " + str(name))
        return _tool_governance_summary(name, definition)

    def timeout_seconds(self, name: str) -> float | None:
        """Return a declared per-tool timeout, if the tool has one."""
        return self.governance_for(name).get("timeout_seconds")

    def data_dependencies(self, name: str, arguments: Mapping[str, Any]) -> list[str]:
        """Resolve declared dataset dependencies against call arguments."""
        dependencies = self.governance_for(name).get("data_dependencies") or []
        resolved = []
        for dependency in dependencies:
            value = str(dependency)
            if value.startswith("$"):
                argument_name = value[1:]
                argument_value = arguments.get(argument_name)
                if isinstance(argument_value, str) and argument_value:
                    value = argument_value
                else:
                    continue
            if value not in resolved:
                resolved.append(value)
        return resolved

    def invoke(
        self,
        name: str,
        arguments: Dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Dict[str, Any]:
        definition = self._definitions.get(name)
        if definition is None:
            raise ToolError("Unknown tool: " + name)
        if self._approval_guard is not None:
            self._approval_guard(definition)
        self.validate_arguments(name, arguments)
        effective_timeout = timeout_seconds
        if effective_timeout is not None:
            try:
                effective_timeout = float(effective_timeout)
            except (TypeError, ValueError) as exc:
                raise ToolError("timeout_seconds must be positive") from exc
            if effective_timeout <= 0:
                raise ToolError("timeout_seconds must be positive")
        if effective_timeout is None:
            return self._invoke_unbounded(name, arguments)

        # A provider may block in native code or in a network call. A daemon
        # thread gives the Runtime a real bounded wait without making the
        # process wait for a stuck provider during interpreter shutdown.
        outcome: Dict[str, Any] = {}
        completed = Event()

        def dispatch() -> None:
            try:
                outcome["result"] = self._invoke_unbounded(name, arguments)
            except BaseException as exc:  # propagate the provider error on caller thread
                outcome["error"] = exc
            finally:
                completed.set()

        Thread(
            target=dispatch,
            name="spatial-agent-tool-" + str(name),
            daemon=True,
        ).start()
        started = monotonic()
        if not completed.wait(effective_timeout):
            raise ToolError(
                "Tool execution timed out: " + name,
                category="timeout",
                code="tool_timeout",
                retryable=False,
            )
        error = outcome.get("error")
        if error is not None:
            raise error
        result = outcome.get("result")
        if monotonic() - started > effective_timeout:
            raise ToolError(
                "Tool execution timed out: " + name,
                category="timeout",
                code="tool_timeout",
                retryable=False,
            )
        return result

    def validate_arguments(self, name: str, arguments: Dict[str, Any]) -> None:
        """Validate one call against the Registry-owned input schema."""
        definition = self._definitions.get(name)
        if definition is None:
            raise ToolError("Unknown tool: " + str(name))
        schema = definition.get("input_schema", {})
        self._validate(arguments, schema, "$")

    def result_type_for_tool(self, name: str) -> str | None:
        """Return an explicitly declared output result type, when present."""
        definition = self._definitions.get(name)
        if not isinstance(definition, Mapping):
            raise ToolError("Unknown tool: " + str(name))
        schema = definition.get("output_schema")
        if not isinstance(schema, Mapping):
            return None
        properties = schema.get("properties")
        result_type = properties.get("result_type") if isinstance(properties, Mapping) else None
        if isinstance(result_type, Mapping) and result_type.get("const"):
            return str(result_type["const"])[:96]
        declared = schema.get("result_type")
        return str(declared)[:96] if isinstance(declared, str) and declared.strip() else None

    def _invoke_unbounded(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
            result = self._provider.invoke(name, arguments)
        except ToolProviderError as exc:
            raise ToolError(
                str(exc),
                category=exc.category or "provider",
                code=exc.code or "provider_error",
                retryable=exc.retryable,
            ) from exc
        except ToolError as exc:
            if "does not implement" in str(exc) and name in self._definitions:
                # A static definition without an adapter implementation is a
                # configuration error, not a dynamic tool.
                raise
            raise
        except Exception as exc:
            raise ToolError(
                "Tool execution failed: " + str(exc),
                category="provider",
                code="provider_execution",
            ) from exc
        if not isinstance(result, dict):
            raise ToolError("Tool must return an object: " + name)
        return result

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        exporter = getattr(self._provider, "export_result", None)
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


def _schema_property_summary(schema: Mapping[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"type": str(schema.get("type", "any"))}
    if isinstance(schema.get("enum"), list):
        summary["enum"] = [str(value) for value in schema.get("enum", [])[:16]]
    for key in ("minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength"):
        if key in schema:
            summary[key] = schema.get(key)
    return summary


def _tool_governance_summary(name: str, definition: Mapping[str, Any]) -> Dict[str, Any]:
    def bounded_list(value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            return []
        return [str(item)[:96] for item in list(value)[:12] if item is not None]

    dependencies = definition.get("data_dependencies")
    if dependencies is None:
        dependencies = definition.get("required_datasets")
    timeout = definition.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        timeout = None
    return {
        "name": str(name)[:96],
        "side_effect": str(definition.get("side_effect") or "unknown")[:32],
        "requires_approval": bool(definition.get("requires_approval", False)),
        "permissions": bounded_list(definition.get("permissions")),
        "data_dependencies": bounded_list(dependencies),
        "timeout_seconds": float(timeout) if timeout is not None else None,
    }


def __getattr__(name: str):
    """Lazily expose the historical GIS demo adapter without a Domain import."""
    if name == "DemoSpatialAdapter":
        from domains.gis.adapters.demo_tool import DemoSpatialAdapter

        return DemoSpatialAdapter
    raise AttributeError(name)
