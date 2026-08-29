"""Bounded Unix-socket transport for the Python proposal sandbox."""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping
from typing import Any


SANDBOX_PROTOCOL_SCHEMA_VERSION = "spatial-agent.tool-proposal-sandbox.v1"
_MAX_REQUEST_BYTES = 128 * 1024
_MAX_RESPONSE_BYTES = 256 * 1024


class SandboxClientError(RuntimeError):
    """A safe, classified sidecar transport failure."""

    def __init__(self, message: str, *, code: str = "sandbox_unavailable") -> None:
        super().__init__(message)
        self.code = str(code)[:96]


class UnixSocketSandboxClient:
    """Call one local sidecar request with a bounded JSON-line protocol."""

    def __init__(self, socket_path: str, *, timeout_seconds: float = 3.0) -> None:
        self._socket_path = str(socket_path or "")[:255]
        try:
            self._timeout_seconds = max(1.0, min(float(timeout_seconds), 10.0))
        except (TypeError, ValueError):
            self._timeout_seconds = 3.0

    def validate_and_run(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(proposal, Mapping):
            raise SandboxClientError(
                "sandbox proposal must be an object", code="sandbox_request_invalid"
            )
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
            if key in proposal
        }
        envelope = {
            "schema_version": SANDBOX_PROTOCOL_SCHEMA_VERSION,
            "operation": "validate_and_run",
            "proposal": public_fields,
        }
        try:
            request = json.dumps(
                envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SandboxClientError(
                "sandbox request is not JSON serializable",
                code="sandbox_request_invalid",
            ) from exc
        if len(request) > _MAX_REQUEST_BYTES:
            raise SandboxClientError(
                "sandbox request is too large", code="sandbox_request_too_large"
            )
        if not self._socket_path:
            raise SandboxClientError("sandbox socket is not configured")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self._timeout_seconds)
                connection.connect(self._socket_path)
                connection.sendall(request + b"\n")
                payload = _receive_line(connection)
        except socket.timeout as exc:
            raise SandboxClientError(
                "sandbox request timed out", code="sandbox_timeout"
            ) from exc
        except (OSError, ValueError) as exc:
            raise SandboxClientError("sandbox is unavailable") from exc
        try:
            response = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SandboxClientError(
                "sandbox response is invalid", code="sandbox_invalid_response"
            ) from exc
        if not isinstance(response, Mapping):
            raise SandboxClientError(
                "sandbox response must be an object", code="sandbox_invalid_response"
            )
        if response.get("schema_version") != SANDBOX_PROTOCOL_SCHEMA_VERSION:
            raise SandboxClientError(
                "sandbox protocol is unsupported", code="sandbox_protocol_invalid"
            )
        return {
            key: response[key]
            for key in (
                "status",
                "reason_code",
                "checks",
                "output_bytes",
                "sandbox_profile",
            )
            if key in response
        }

    def execute_proposal(
        self,
        proposal_id: str,
        source_hash: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Execute a previously validated proposal held by the sidecar.

        The main process sends only the proposal identity and JSON arguments.
        Source remains in the sidecar's bounded volatile cache and is never
        persisted in an approval record or accepted from this operation.
        """
        if not isinstance(arguments, Mapping):
            raise SandboxClientError(
                "sandbox arguments must be an object", code="sandbox_request_invalid"
            )
        envelope = {
            "schema_version": SANDBOX_PROTOCOL_SCHEMA_VERSION,
            "operation": "execute",
            "proposal_ref": {
                "proposal_id": str(proposal_id or "")[:96],
                "source_hash": str(source_hash or "")[:96],
            },
            "arguments": dict(arguments),
        }
        response = self._exchange(envelope)
        return {
            key: response[key]
            for key in (
                "status",
                "reason_code",
                "checks",
                "output_bytes",
                "sandbox_profile",
                "result",
            )
            if key in response
        }

    def _exchange(self, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            request = json.dumps(
                envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SandboxClientError(
                "sandbox request is not JSON serializable",
                code="sandbox_request_invalid",
            ) from exc
        if len(request) > _MAX_REQUEST_BYTES:
            raise SandboxClientError(
                "sandbox request is too large", code="sandbox_request_too_large"
            )
        if not self._socket_path:
            raise SandboxClientError("sandbox socket is not configured")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self._timeout_seconds)
                connection.connect(self._socket_path)
                connection.sendall(request + b"\n")
                payload = _receive_line(connection)
        except socket.timeout as exc:
            raise SandboxClientError(
                "sandbox request timed out", code="sandbox_timeout"
            ) from exc
        except (OSError, ValueError) as exc:
            raise SandboxClientError("sandbox is unavailable") from exc
        try:
            response = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SandboxClientError(
                "sandbox response is invalid", code="sandbox_invalid_response"
            ) from exc
        if not isinstance(response, Mapping):
            raise SandboxClientError(
                "sandbox response must be an object", code="sandbox_invalid_response"
            )
        if response.get("schema_version") != SANDBOX_PROTOCOL_SCHEMA_VERSION:
            raise SandboxClientError(
                "sandbox protocol is unsupported", code="sandbox_protocol_invalid"
            )
        return response


def _receive_line(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while size <= _MAX_RESPONSE_BYTES:
        chunk = connection.recv(min(16 * 1024, _MAX_RESPONSE_BYTES - size + 1))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if b"\n" in chunk:
            break
    payload = b"".join(chunks).split(b"\n", 1)[0]
    if not payload or len(payload) > _MAX_RESPONSE_BYTES:
        raise SandboxClientError(
            "sandbox response is too large", code="sandbox_response_too_large"
        )
    return payload


__all__ = [
    "SANDBOX_PROTOCOL_SCHEMA_VERSION",
    "SandboxClientError",
    "UnixSocketSandboxClient",
]
