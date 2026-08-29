"""One-shot child process used inside the proposal sandbox sidecar.

The runner receives a normalized proposal over stdin and emits only a bounded
validation receipt. It is intentionally separate from the long-lived worker so
each generated function gets a fresh interpreter and resource limits.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            return _write({"status": "rejected", "reason_code": "sandbox_request_too_large"})
        envelope = json.loads(raw.decode("utf-8"))
        proposal = envelope.get("proposal") if isinstance(envelope, dict) else None
        _add_project_root()
        from agent.tooling.proposal import (
            ProposalValidationError,
            _validate_json_shape,
            normalize_tool_proposal,
            validate_json_value,
            validate_source_ast,
        )

        try:
            public_fields = {
                key: proposal[key]
                for key in (
                    "name",
                    "description",
                    "input_schema",
                    "output_schema",
                    "source",
                    "example_arguments",
                )
                if isinstance(proposal, dict) and key in proposal
            }
            normalized = normalize_tool_proposal(public_fields)
        except ProposalValidationError as exc:
            return _write({"status": "rejected", "reason_code": exc.code})
        ast_result = validate_source_ast(normalized["source"])
        if ast_result.get("status") != "passed":
            return _write(
                {
                    "status": "rejected",
                    "reason_code": ast_result.get("reason_code") or "proposal_ast_invalid",
                    "checks": {"ast": "rejected", "execution": "not_run"},
                }
            )
        try:
            namespace = {"__builtins__": _safe_builtins()}
            exec(compile(normalized["source"], "<tool-proposal>", "exec"), namespace, namespace)
            function = namespace.get("run")
            if not callable(function):
                return _write({"status": "rejected", "reason_code": "proposal_entrypoint_invalid"})
            output = function(normalized["example_arguments"])
            _validate_json_shape(output, max_depth=8, max_bytes=1024 * 1024)
            validate_json_value(
                output,
                normalized["output_schema"],
                code="proposal_output_schema_invalid",
            )
            encoded = json.dumps(
                output, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            if len(encoded) > 1024 * 1024:
                return _write({"status": "rejected", "reason_code": "proposal_output_too_large"})
        except ProposalValidationError as exc:
            return _write({"status": "rejected", "reason_code": exc.code})
        except MemoryError:
            return _write({"status": "rejected", "reason_code": "proposal_memory_limit"})
        except TimeoutError:
            return _write({"status": "rejected", "reason_code": "proposal_execution_timeout"})
        except Exception:
            return _write({"status": "rejected", "reason_code": "proposal_execution_failed"})
        response = {
            "status": "validated",
            "reason_code": "proposal_validated",
            "output_bytes": len(encoded),
            "checks": {"ast": "passed", "execution": "passed", "output_schema": "passed"},
        }
        if isinstance(envelope, dict) and envelope.get("operation") == "execute":
            response["result"] = output
        return _write(response)
    except Exception:
        return _write({"status": "unavailable", "reason_code": "sandbox_runner_failed"})


def _safe_builtins() -> dict[str, Any]:
    names = (
        "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
        "int", "len", "list", "map", "max", "min", "range", "round", "sorted",
        "str", "sum", "tuple", "zip",
    )
    import builtins

    return {name: getattr(builtins, name) for name in names}


def _add_project_root() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if root not in sys.path:
        sys.path.insert(0, root)


def _write(value: dict[str, Any]) -> int:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(payload[:32 * 1024])
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
