"""Long-lived Unix socket worker for isolated Python tool proposal checks."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from typing import Any

from .proposal import (
    ProposalValidationError,
    normalize_tool_proposal,
    validate_source_ast,
)
from .sandbox import SANDBOX_PROTOCOL_SCHEMA_VERSION


_MAX_REQUEST_BYTES = 128 * 1024
_MAX_CHILD_OUTPUT_BYTES = 64 * 1024
_DEFAULT_SOCKET = "/run/spatial-agent-sandbox/worker.sock"


def main() -> int:
    socket_path = str(os.environ.get("SPATIAL_AGENT_TOOL_PROPOSAL_SANDBOX_SOCKET") or _DEFAULT_SOCKET)
    timeout_seconds = _bounded_float(
        os.environ.get("SPATIAL_AGENT_TOOL_PROPOSAL_SANDBOX_TIMEOUT_SECONDS"), 3.0, 1.0, 10.0
    )
    _prepare_socket_path(socket_path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(socket_path)
        os.chmod(socket_path, 0o660)
        server.listen(8)
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(timeout_seconds + 1.0)
                try:
                    payload = _read_line(connection)
                    response = _handle(payload, timeout_seconds)
                except (OSError, ValueError):
                    response = _response("rejected", "sandbox_request_invalid")
                try:
                    connection.sendall(_encode_response(response))
                except BrokenPipeError:
                    # Health checks and abruptly disconnected clients do not
                    # justify terminating the long-lived worker.
                    pass


def _handle(payload: bytes, timeout_seconds: float) -> dict[str, Any]:
    try:
        envelope = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _response("rejected", "sandbox_request_invalid")
    if not isinstance(envelope, Mapping) or envelope.get("schema_version") != SANDBOX_PROTOCOL_SCHEMA_VERSION:
        return _response("rejected", "sandbox_protocol_invalid")
    if envelope.get("operation") != "validate_and_run":
        return _response("rejected", "sandbox_operation_invalid")
    proposal = envelope.get("proposal")
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
            if isinstance(proposal, Mapping) and key in proposal
        }
        normalized = normalize_tool_proposal(public_fields)
    except ProposalValidationError as exc:
        return _response("rejected", exc.code, checks={"normalization": "rejected"})
    ast_result = validate_source_ast(normalized["source"])
    if ast_result.get("status") != "passed":
        return _response(
            "rejected",
            ast_result.get("reason_code") or "proposal_ast_invalid",
            checks={"normalization": "passed", "ast": "rejected", "execution": "not_run"},
        )
    child_input = json.dumps(
        {"schema_version": SANDBOX_PROTOCOL_SCHEMA_VERSION, "proposal": normalized},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", os.path.join(os.path.dirname(__file__), "sandbox_runner.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=_set_resource_limits,
        )
        stdout, _ = process.communicate(child_input, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        return _response(
            "rejected",
            "proposal_execution_timeout",
            checks={"normalization": "passed", "ast": "passed", "execution": "timeout"},
            duration_ms=(time.monotonic() - started) * 1000.0,
        )
    except (OSError, ValueError):
        return _response(
            "unavailable",
            "sandbox_runner_unavailable",
            checks={"normalization": "passed", "ast": "passed", "execution": "unavailable"},
            duration_ms=(time.monotonic() - started) * 1000.0,
        )
    if len(stdout) > _MAX_CHILD_OUTPUT_BYTES:
        return _response("rejected", "sandbox_runner_output_too_large")
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _response("unavailable", "sandbox_runner_invalid_response")
    if not isinstance(result, Mapping):
        return _response("unavailable", "sandbox_runner_invalid_response")
    status = result.get("status")
    if status not in {"validated", "rejected", "unavailable"}:
        status = "unavailable"
    response = _response(
        status,
        result.get("reason_code") or "sandbox_runner_failed",
        checks=result.get("checks"),
        output_bytes=result.get("output_bytes", 0),
        duration_ms=(time.monotonic() - started) * 1000.0,
    )
    if process.returncode not in {0, None} and response["status"] == "validated":
        response["status"] = "unavailable"
        response["reason_code"] = "sandbox_runner_failed"
    return response


def _response(status: str, reason_code: Any, *, checks: Any = None, output_bytes: Any = 0, duration_ms: Any = 0) -> dict[str, Any]:
    try:
        output_size = max(0, min(int(output_bytes), 1024 * 1024))
    except (TypeError, ValueError):
        output_size = 0
    try:
        duration = max(0.0, min(float(duration_ms), 60_000.0))
    except (TypeError, ValueError):
        duration = 0.0
    safe_checks = {}
    if isinstance(checks, Mapping):
        safe_checks = {str(key)[:48]: str(value)[:32] for key, value in list(checks.items())[:12]}
    return {
        "schema_version": SANDBOX_PROTOCOL_SCHEMA_VERSION,
        "status": status if status in {"validated", "rejected", "unavailable"} else "unavailable",
        "reason_code": str(reason_code or "sandbox_failed")[:96],
        "checks": safe_checks,
        "output_bytes": output_size,
        "sandbox_profile": {
            "name": "python-pure-v1",
            "network": "none",
            "filesystem": "read-only",
            "timeout_seconds": 3.0,
        },
        "duration_ms": round(duration, 2),
    }


def _read_line(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= _MAX_REQUEST_BYTES:
        chunk = connection.recv(min(16 * 1024, _MAX_REQUEST_BYTES - total + 1))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
    value = b"".join(chunks).split(b"\n", 1)[0]
    if not value or len(value) > _MAX_REQUEST_BYTES:
        raise ValueError("sandbox request too large")
    return value


def _encode_response(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:64 * 1024] + "\n").encode("utf-8")


def _prepare_socket_path(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, mode=0o770, exist_ok=True)
    if os.path.exists(path):
        if not stat_is_socket(path):
            raise RuntimeError("sandbox socket path is not a socket")
        os.unlink(path)


def stat_is_socket(path: str) -> bool:
    return socket is not None and os.path.exists(path) and __import__("stat").S_ISSOCK(os.stat(path).st_mode)


def _set_resource_limits() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (3, 4))
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    resource.setrlimit(resource.RLIMIT_NPROC, (8, 8))


def _terminate_process(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.communicate(timeout=1)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum)) if value == value else default


if __name__ == "__main__":
    raise SystemExit(main())
