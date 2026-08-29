"""Bounded contracts and local validation for generated Python tools.

This module never executes proposal source.  Execution is delegated to the
separate Unix-socket sandbox client after the same static checks are repeated
inside the worker.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from time import monotonic
from typing import Any


TOOL_PROPOSAL_SCHEMA_VERSION = "spatial-agent.tool-proposal.v1"
TOOL_PROPOSAL_RECEIPT_SCHEMA_VERSION = "spatial-agent.tool-proposal-receipt.v1"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_SOURCE_BYTES = 48 * 1024
_MAX_DESCRIPTION = 400
_MAX_SCHEMA_BYTES = 16 * 1024
_MAX_SCHEMA_NODES = 128
_MAX_SCHEMA_DEPTH = 8
_MAX_EXAMPLE_BYTES = 16 * 1024
_MAX_EXAMPLE_DEPTH = 8
_MAX_OUTPUT_BYTES = 1024 * 1024
_MAX_AST_NODES = 1200
_MAX_AST_DEPTH = 18
_MAX_LOOPS = 12
_SAFE_CALLS = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "filter",
        "float",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "range",
        "round",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    }
)
_SCHEMA_KEYS = frozenset(
    {
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
    }
)
_JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


class ProposalValidationError(ValueError):
    """A stable, bounded proposal validation failure."""

    def __init__(self, message: str, *, code: str = "proposal_invalid") -> None:
        super().__init__(message)
        self.code = str(code)[:96]


def normalize_tool_proposal(
    value: Any,
    *,
    existing_tools: Any = (),
) -> dict[str, Any]:
    """Normalize one model proposal without executing its source."""

    if not isinstance(value, Mapping):
        raise ProposalValidationError("proposal must be an object")
    allowed = {
        "name",
        "description",
        "input_schema",
        "output_schema",
        "source",
        "example_arguments",
    }
    if set(value) - allowed:
        raise ProposalValidationError(
            "proposal contains unknown fields", code="proposal_unknown_fields"
        )
    name = value.get("name")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name.strip()):
        raise ProposalValidationError(
            "proposal name is invalid", code="proposal_name_invalid"
        )
    name = name.strip()[:96]
    names = {str(item) for item in (existing_tools or ())}
    if name in names:
        raise ProposalValidationError(
            "proposal name already exists", code="proposal_name_conflict"
        )
    description = value.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ProposalValidationError(
            "proposal description is required", code="proposal_description_invalid"
        )
    source = value.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ProposalValidationError(
            "proposal source is required", code="proposal_source_missing"
        )
    source = source.strip()
    if len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        raise ProposalValidationError(
            "proposal source is too large", code="proposal_source_too_large"
        )
    input_schema = _normalize_schema(value.get("input_schema"), "input_schema")
    output_schema = _normalize_schema(value.get("output_schema"), "output_schema")
    example = value.get("example_arguments")
    if not isinstance(example, dict):
        raise ProposalValidationError(
            "example_arguments must be an object", code="proposal_example_invalid"
        )
    _validate_json_shape(example, max_depth=_MAX_EXAMPLE_DEPTH, max_bytes=_MAX_EXAMPLE_BYTES)
    validate_json_value(example, input_schema, code="proposal_example_invalid")
    schemas = {"input_schema": input_schema, "output_schema": output_schema}
    schema_hash = _sha256_json(schemas)
    source_hash = _sha256_text(source)
    proposal_id = "proposal-" + hashlib.sha256(
        (name + ":" + source_hash + ":" + schema_hash).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "schema_version": TOOL_PROPOSAL_SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "name": name,
        "description": description.strip()[:_MAX_DESCRIPTION],
        "input_schema": input_schema,
        "output_schema": output_schema,
        "source": source,
        "example_arguments": deepcopy(example),
        "source_hash": source_hash,
        "schema_hash": schema_hash,
    }


def validate_source_ast(source: str) -> dict[str, Any]:
    """Apply a conservative pure-Python AST policy before sandbox execution."""

    if not isinstance(source, str) or not source.strip():
        return {"status": "rejected", "reason_code": "proposal_source_missing"}
    if len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        return {"status": "rejected", "reason_code": "proposal_source_too_large"}
    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, TypeError):
        return {"status": "rejected", "reason_code": "proposal_source_syntax_invalid"}
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        return {"status": "rejected", "reason_code": "proposal_ast_too_large"}
    if max((_ast_depth(node) for node in nodes), default=0) > _MAX_AST_DEPTH:
        return {"status": "rejected", "reason_code": "proposal_ast_too_deep"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "run":
        return {"status": "rejected", "reason_code": "proposal_entrypoint_invalid"}
    function = functions[0]
    if function.decorator_list or function.type_comment:
        return {"status": "rejected", "reason_code": "proposal_decorator_forbidden"}
    args = function.args
    positional = [*args.posonlyargs, *args.args]
    if len(positional) != 1 or positional[0].arg != "arguments":
        return {"status": "rejected", "reason_code": "proposal_signature_invalid"}
    if args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults:
        return {"status": "rejected", "reason_code": "proposal_signature_invalid"}
    top_level_constants = set()
    for item in tree.body:
        if isinstance(item, ast.Assign):
            if not item.targets or not all(
                isinstance(target, ast.Name) and not target.id.startswith("__")
                for target in item.targets
            ):
                return {"status": "rejected", "reason_code": "proposal_global_assignment_invalid"}
            if not _literal_only(item.value):
                return {"status": "rejected", "reason_code": "proposal_global_not_constant"}
            top_level_constants.update(target.id for target in item.targets)
        elif isinstance(item, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef)):
            return {"status": "rejected", "reason_code": "proposal_ast_forbidden_node"}
        elif item is not function:
            if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                continue
            return {"status": "rejected", "reason_code": "proposal_top_level_statement_forbidden"}

    forbidden = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.AsyncFunctionDef,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.Raise,
        ast.Global,
        ast.Nonlocal,
        ast.Lambda,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.Delete,
        ast.NamedExpr,
    )
    loop_count = 0
    for node in ast.walk(function):
        if isinstance(node, forbidden):
            return {
                "status": "rejected",
                "reason_code": "proposal_ast_forbidden_node",
            }
        if isinstance(node, (ast.For, ast.While, ast.comprehension)):
            loop_count += 1
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return {"status": "rejected", "reason_code": "proposal_dunder_forbidden"}
        if isinstance(node, ast.Attribute):
            return {"status": "rejected", "reason_code": "proposal_attribute_forbidden"}
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_CALLS:
                return {"status": "rejected", "reason_code": "proposal_call_forbidden"}
        if isinstance(node, ast.Constant) and isinstance(node.value, (bytes, complex)):
            return {"status": "rejected", "reason_code": "proposal_constant_forbidden"}
    if loop_count > _MAX_LOOPS:
        return {"status": "rejected", "reason_code": "proposal_loop_budget_exceeded"}
    if not any(isinstance(node, ast.Return) for node in ast.walk(function)):
        return {"status": "rejected", "reason_code": "proposal_return_missing"}
    return {
        "status": "passed",
        "reason_code": "proposal_ast_valid",
        "node_count": min(len(nodes), _MAX_AST_NODES),
        "loop_count": min(loop_count, _MAX_LOOPS),
    }


def validate_json_value(
    value: Any,
    schema: Mapping[str, Any],
    *,
    code: str = "proposal_output_schema_invalid",
    path: str = "$",
) -> None:
    """Validate the small JSON Schema subset accepted for proposals."""

    if not isinstance(schema, Mapping):
        raise ProposalValidationError("schema must be an object", code=code)
    expected = schema.get("type")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected not in valid or not valid[expected]:
        raise ProposalValidationError(
            path + " does not match schema type", code=code
        )
    if "const" in schema and value != schema["const"]:
        raise ProposalValidationError(path + " does not match const", code=code)
    if "enum" in schema and value not in schema.get("enum", []):
        raise ProposalValidationError(path + " is not in enum", code=code)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ProposalValidationError(path + " is below minimum", code=code)
        if "maximum" in schema and value > schema["maximum"]:
            raise ProposalValidationError(path + " is above maximum", code=code)
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ProposalValidationError(path + " is shorter than minLength", code=code)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ProposalValidationError(path + " is longer than maxLength", code=code)
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ProposalValidationError(path + " has too few items", code=code)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ProposalValidationError(path + " has too many items", code=code)
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value[:64]):
                validate_json_value(item, item_schema, code=code, path=f"{path}[{index}]")
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        missing = [name for name in required if name not in value]
        if missing:
            raise ProposalValidationError(
                path + " missing required fields: " + ", ".join(map(str, missing)),
                code=code,
            )
        if schema.get("additionalProperties") is False:
            extra = [name for name in value if name not in properties]
            if extra:
                raise ProposalValidationError(
                    path + " has unknown fields: " + ", ".join(map(str, extra)),
                    code=code,
                )
        for name, item in value.items():
            child_schema = properties.get(name)
            if isinstance(child_schema, Mapping):
                validate_json_value(item, child_schema, code=code, path=path + "." + str(name))


class ToolProposalValidator:
    """Local preflight plus a separately injected sandbox execution port."""

    def __init__(self, sandbox_client: Any = None) -> None:
        self._sandbox_client = sandbox_client

    def validate(self, proposal: Any, *, existing_tools: Any = ()) -> dict[str, Any]:
        started = monotonic()
        normalized = None
        try:
            normalized = normalize_tool_proposal(proposal, existing_tools=existing_tools)
            ast_result = validate_source_ast(normalized["source"])
            if ast_result.get("status") != "passed":
                return self._receipt(
                    normalized,
                    status="rejected",
                    reason_code=ast_result.get("reason_code"),
                    checks={"normalization": "passed", "ast": "rejected", "sandbox": "not_run"},
                    duration_ms=_duration_ms(started),
                )
        except ProposalValidationError as exc:
            return self._invalid_receipt(proposal, exc.code, started)
        if self._sandbox_client is None:
            return self._receipt(
                normalized,
                status="unavailable",
                reason_code="sandbox_unavailable",
                checks={"normalization": "passed", "ast": "passed", "sandbox": "unavailable"},
                duration_ms=_duration_ms(started),
            )
        try:
            response = self._sandbox_client.validate_and_run(normalized)
        except Exception as exc:
            return self._receipt(
                normalized,
                status="unavailable",
                reason_code=str(getattr(exc, "code", None) or "sandbox_unavailable")[:96],
                checks={"normalization": "passed", "ast": "passed", "sandbox": "unavailable"},
                duration_ms=_duration_ms(started),
            )
        if not isinstance(response, Mapping):
            return self._receipt(
                normalized,
                status="unavailable",
                reason_code="sandbox_invalid_response",
                checks={"normalization": "passed", "ast": "passed", "sandbox": "invalid"},
                duration_ms=_duration_ms(started),
            )
        status = response.get("status")
        if status not in {"validated", "rejected", "unavailable"}:
            status = "unavailable"
        return self._receipt(
            normalized,
            status=status,
            reason_code=response.get("reason_code") or (
                "proposal_validated" if status == "validated" else "sandbox_rejected"
            ),
            checks={
                "normalization": "passed",
                "ast": "passed",
                "sandbox": "passed" if status == "validated" else status,
                **(
                    dict(response.get("checks"))
                    if isinstance(response.get("checks"), Mapping)
                    else {}
                ),
            },
            output_bytes=response.get("output_bytes"),
            sandbox_profile=response.get("sandbox_profile"),
            duration_ms=_duration_ms(started),
        )

    def handler_for(self, approval: Mapping[str, Any]):
        """Build a controlled handler from an approved public record.

        The handler references the sidecar cache by identity.  It never reads
        source from the approval record and therefore fails closed when the
        sidecar was restarted before the proposal was published.
        """
        if self._sandbox_client is None:
            return None
        execute = getattr(self._sandbox_client, "execute_proposal", None)
        if not callable(execute):
            return None
        proposal_id = str(approval.get("proposal_id") or "")[:96]
        source_hash = str(approval.get("source_hash") or "")[:96]
        if not proposal_id or not source_hash:
            return None

        def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            response = execute(proposal_id, source_hash, arguments)
            if not isinstance(response, Mapping) or response.get("status") != "validated":
                reason = str(
                    response.get("reason_code")
                    if isinstance(response, Mapping)
                    else "sandbox_execution_unavailable"
                )[:96]
                raise ProposalValidationError(
                    "approved tool execution is unavailable: " + reason,
                    code="approved_tool_execution_unavailable",
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise ProposalValidationError(
                    "approved tool returned an invalid result",
                    code="approved_tool_result_invalid",
                )
            return result

        return invoke

    def _invalid_receipt(self, proposal: Any, reason_code: str, started: float) -> dict[str, Any]:
        name = str(proposal.get("name") if isinstance(proposal, Mapping) else "")[:96]
        return build_proposal_receipt(
            proposal_id=None,
            name=name,
            status="rejected",
            source_hash=None,
            schema_hash=None,
            checks={"normalization": "rejected", "ast": "not_run", "sandbox": "not_run"},
            duration_ms=_duration_ms(started),
            reason_code=reason_code,
        )

    def _receipt(self, proposal: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        return build_proposal_receipt(
            proposal_id=proposal.get("proposal_id"),
            name=proposal.get("name"),
            source_hash=proposal.get("source_hash"),
            schema_hash=proposal.get("schema_hash"),
            definition=_proposal_definition(proposal),
            **kwargs,
        )


def build_proposal_receipt(
    *,
    proposal_id: Any,
    name: Any,
    status: str,
    source_hash: Any,
    schema_hash: Any,
    checks: Any = None,
    duration_ms: Any = 0,
    output_bytes: Any = 0,
    reason_code: Any = None,
    sandbox_profile: Any = None,
    definition: Any = None,
) -> dict[str, Any]:
    """Build the only proposal payload allowed beyond the validation seam."""

    if status not in {"validated", "rejected", "unavailable"}:
        status = "unavailable"
    try:
        duration = max(0.0, min(float(duration_ms), 60_000.0))
    except (TypeError, ValueError):
        duration = 0.0
    try:
        output_size = max(0, min(int(output_bytes), _MAX_OUTPUT_BYTES))
    except (TypeError, ValueError):
        output_size = 0
    safe_checks = {}
    if isinstance(checks, Mapping):
        for key, value in list(checks.items())[:12]:
            safe_checks[str(key)[:48]] = str(value)[:32]
    profile = sandbox_profile if isinstance(sandbox_profile, Mapping) else {}
    safe_profile = {
        "name": str(profile.get("name") or "python-pure-v1")[:64],
        "network": "none",
        "filesystem": "read-only",
        "timeout_seconds": _finite_float(profile.get("timeout_seconds"), 3.0, 0.1, 30.0),
    }
    receipt = {
        "schema_version": TOOL_PROPOSAL_RECEIPT_SCHEMA_VERSION,
        "proposal_id": str(proposal_id or "")[:96] or None,
        "name": str(name or "")[:96] or None,
        "status": status,
        "source_hash": str(source_hash or "")[:96] or None,
        "schema_hash": str(schema_hash or "")[:96] or None,
        "checks": safe_checks,
        "duration_ms": round(duration, 2),
        "output_bytes": output_size,
        "reason_code": str(reason_code or "")[:96] or None,
        "sandbox_profile": safe_profile,
    }
    if isinstance(definition, Mapping):
        receipt["definition"] = _proposal_definition(definition)
    return receipt


def _proposal_definition(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Project Registry metadata without source or example arguments."""

    result: dict[str, Any] = {
        "name": str(proposal.get("name") or "")[:96],
        "description": str(proposal.get("description") or "")[:_MAX_DESCRIPTION],
        "input_schema": deepcopy(proposal.get("input_schema"))
        if isinstance(proposal.get("input_schema"), Mapping)
        else {"type": "object"},
        "output_schema": deepcopy(proposal.get("output_schema"))
        if isinstance(proposal.get("output_schema"), Mapping)
        else {"type": "object"},
        "dynamic": True,
        "requires_approval": True,
        "side_effect": "unknown",
        "handler_ref": "proposal:" + str(proposal.get("proposal_id") or "")[:96],
    }
    return result


def _normalize_schema(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("type") != "object":
        raise ProposalValidationError(
            field_name + " must be an object schema", code="proposal_schema_invalid"
        )
    schema = deepcopy(dict(value))
    _validate_schema_document(schema, field_name, depth=0, counter=[0])
    try:
        encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ProposalValidationError(
            field_name + " is not JSON serializable", code="proposal_schema_invalid"
        ) from exc
    if len(encoded.encode("utf-8")) > _MAX_SCHEMA_BYTES:
        raise ProposalValidationError(
            field_name + " is too large", code="proposal_schema_too_large"
        )
    return schema


def _validate_schema_document(value: Mapping[str, Any], field_name: str, *, depth: int, counter: list[int]) -> None:
    if depth > _MAX_SCHEMA_DEPTH:
        raise ProposalValidationError(field_name + " is too deep", code="proposal_schema_too_deep")
    counter[0] += 1
    if counter[0] > _MAX_SCHEMA_NODES:
        raise ProposalValidationError(field_name + " has too many nodes", code="proposal_schema_too_large")
    unknown = set(value) - _SCHEMA_KEYS
    if unknown:
        raise ProposalValidationError(field_name + " has unsupported keywords", code="proposal_schema_keyword_forbidden")
    schema_type = value.get("type")
    if schema_type not in _JSON_TYPES:
        raise ProposalValidationError(field_name + " has invalid type", code="proposal_schema_invalid")
    if "properties" in value:
        properties = value["properties"]
        if not isinstance(properties, Mapping):
            raise ProposalValidationError(field_name + ".properties must be an object", code="proposal_schema_invalid")
        for name, child in list(properties.items())[:64]:
            if not isinstance(name, str) or not name or len(name) > 96 or not isinstance(child, Mapping):
                raise ProposalValidationError(field_name + ".properties is invalid", code="proposal_schema_invalid")
            _validate_schema_document(child, field_name + ".properties." + name, depth=depth + 1, counter=counter)
    if "required" in value:
        required = value["required"]
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ProposalValidationError(field_name + ".required is invalid", code="proposal_schema_invalid")
        properties = value.get("properties") if isinstance(value.get("properties"), Mapping) else {}
        if any(item not in properties for item in required):
            raise ProposalValidationError(field_name + ".required references unknown field", code="proposal_schema_invalid")
    if "items" in value:
        if not isinstance(value["items"], Mapping):
            raise ProposalValidationError(field_name + ".items is invalid", code="proposal_schema_invalid")
        _validate_schema_document(value["items"], field_name + ".items", depth=depth + 1, counter=counter)
    if value.get("additionalProperties") not in {None, True, False}:
        raise ProposalValidationError(field_name + ".additionalProperties is invalid", code="proposal_schema_invalid")


def _validate_json_shape(value: Any, *, max_depth: int, max_bytes: int, depth: int = 0) -> None:
    if depth > max_depth:
        raise ProposalValidationError("JSON value is too deep", code="proposal_example_too_deep")
    if isinstance(value, Mapping):
        if len(value) > 64:
            raise ProposalValidationError("JSON object is too large", code="proposal_example_too_large")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 96:
                raise ProposalValidationError("JSON key is invalid", code="proposal_example_invalid")
            _validate_json_shape(item, max_depth=max_depth, max_bytes=max_bytes, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 128:
            raise ProposalValidationError("JSON array is too large", code="proposal_example_too_large")
        for item in value:
            _validate_json_shape(item, max_depth=max_depth, max_bytes=max_bytes, depth=depth + 1)
    elif isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ProposalValidationError("JSON number is invalid", code="proposal_example_invalid")
    else:
        raise ProposalValidationError("JSON value is not supported", code="proposal_example_invalid")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ProposalValidationError("JSON value is invalid", code="proposal_example_invalid") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ProposalValidationError("JSON value is too large", code="proposal_example_too_large")


def _literal_only(node: ast.AST) -> bool:
    return all(
        not isinstance(item, (ast.Call, ast.Name, ast.Attribute, ast.Lambda, ast.Starred))
        for item in ast.walk(node)
    )


def _ast_depth(node: ast.AST, depth: int = 0) -> int:
    children = list(ast.iter_child_nodes(node))
    return max([depth, *(_ast_depth(child, depth + 1) for child in children)])


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(encoded)


def _duration_ms(started: float) -> float:
    return min(60_000.0, max(0.0, (monotonic() - started) * 1000.0))


def _finite_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return max(minimum, min(result, maximum))


__all__ = [
    "ProposalValidationError",
    "TOOL_PROPOSAL_RECEIPT_SCHEMA_VERSION",
    "TOOL_PROPOSAL_SCHEMA_VERSION",
    "ToolProposalValidator",
    "build_proposal_receipt",
    "normalize_tool_proposal",
    "validate_json_value",
    "validate_source_ast",
]
