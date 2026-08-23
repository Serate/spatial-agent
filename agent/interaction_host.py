"""Stateful host for authoritative interaction inspection and invocation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .interaction_contract import (
    InteractionContractError,
    normalize_interaction_command,
    project_interaction,
    validate_interaction_command,
)


class InteractionHost:
    """Reload, authorize and dispatch one interaction command.

    ``loader`` must return the current authoritative source for a subject.
    ``dispatcher`` receives a normalized command only after revision, action
    allowlist and input-schema validation.  Durable CAS/idempotency may live in
    the persistence adapter used by the dispatcher; the Host guarantees that
    every transport reaches that adapter through the same checked seam.
    """

    def __init__(
        self,
        loader: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        dispatcher: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        if not callable(loader) or not callable(dispatcher):
            raise TypeError("InteractionHost requires loader and dispatcher callables")
        self._loader = loader
        self._dispatcher = dispatcher

    def inspect(self, subject: Mapping[str, Any]) -> dict[str, Any]:
        """Read and project the latest authoritative interaction."""

        if not isinstance(subject, Mapping):
            raise InteractionContractError(
                "interaction subject must be an object",
                code="interaction_subject_invalid",
            )
        source = self._loader(subject)
        if not isinstance(source, Mapping):
            raise InteractionContractError(
                "interaction subject was not found",
                code="interaction_subject_not_found",
            )
        interaction = project_interaction(source)
        current = interaction.get("subject", {}).get("current", {})
        requested_current = subject.get("current")
        if isinstance(requested_current, Mapping):
            requested_kind = str(requested_current.get("kind") or "")
            requested_id = str(requested_current.get("id") or "")
        else:
            requested_kind = str(subject.get("kind") or "")
            requested_id = str(subject.get("id") or "")
        if requested_kind and requested_id and (
            current.get("kind") != requested_kind or current.get("id") != requested_id
        ):
            raise InteractionContractError(
                "interaction subject identity does not match authoritative state",
                code="interaction_subject_conflict",
            )
        return interaction

    def invoke(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """CAS-check one command and return a response carrying next state."""

        normalized = normalize_interaction_command(command)
        authoritative = self.inspect(normalized["subject"])
        checked = validate_interaction_command(normalized, authoritative)
        response = self._dispatcher(checked, authoritative)
        if not isinstance(response, Mapping):
            raise InteractionContractError(
                "interaction dispatcher returned no response",
                code="interaction_dispatch_invalid",
            )
        result = dict(response)
        # Dispatch may attach a fresh receipt after the Result envelope was
        # initially composed. Reproject from current evidence so the response
        # cannot retain a pre-action interaction snapshot.
        next_interaction = project_interaction(
            result,
            # Run dispatch can attach a receipt after composing its nested
            # Result. Routing dispatch already returns a freshly projected
            # top-level interaction and has no nested Result to refresh.
            prefer_existing=not isinstance(result.get("result"), Mapping),
        )
        result["interaction"] = next_interaction
        nested = result.get("result")
        if isinstance(nested, Mapping):
            nested = dict(nested)
            nested["interaction"] = next_interaction
            result["result"] = nested
        return result


__all__ = ["InteractionHost"]
