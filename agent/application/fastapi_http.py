"""FastAPI transport adapter for the shared HTTP application.

The semantic route contract is owned by :mod:`http` and :mod:`http_routes`.
This module contains only the framework-specific pieces that an ASGI entry
point needs: resolving request-time dependencies, projecting exceptions,
creating streaming/file responses, and reading bounded artifacts.

The dependency provider is deliberately called for every operation.  The
production entry point has historically exposed module-level objects that
tests and local integrations replace at runtime; resolving them lazily keeps
that seam while moving the transport glue out of the entry point.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Mapping, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from agent.application.http import HTTPApplication
from agent.application.http_composition import build_http_application
from agent.application.http_routes import resolve_route
from agent.application.http_transport import (
    error_projection,
    load_artifact_json,
    safe_artifact_path,
)
from agent.domain_http import assert_domain_payload
from agent.run_events import (
    page_contains_terminal_event,
    validate_event_cursor,
    validate_event_limit,
)


DependencyProvider = Callable[[], Mapping[str, Any]]


class FastAPIHttpAdapter:
    """Framework adapter shared by FastAPI route functions.

    ``production_api`` remains responsible for declaring the public routes;
    this object owns all repeated transport-to-application mechanics.  A
    provider is used instead of captured constructor arguments so legacy
    module-level patch points continue to work.
    """

    def __init__(self, dependencies: DependencyProvider):
        self._dependencies = dependencies

    def _deps(self) -> Mapping[str, Any]:
        return self._dependencies()

    def http_application(self, target_service: Any = None) -> HTTPApplication:
        deps = self._deps()
        return build_http_application(
            target_service or deps["service"],
            routing=deps["domain_routing"],
            composite=deps["composite_application"],
            composite_planning=deps["composite_planning_application"],
        )

    def domain_service(
        self,
        domain_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Select the URL domain before validating a redundant body claim."""

        deps = self._deps()
        selection = deps["host"].select(domain_id, source="explicit")
        assert_domain_payload(selection, payload)
        return deps["host"].service(selection)

    def read(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        target_service: Any = None,
    ) -> Dict[str, Any]:
        match = resolve_route("GET", path)
        if match is None:
            raise ValueError("unknown GET route: " + path)
        return self.http_application(target_service).read(
            match.action,
            payload or {},
            resource_id=match.resource_id,
        )

    def execute(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        target_service: Any = None,
    ) -> Dict[str, Any]:
        match = resolve_route("POST", path)
        if match is None:
            raise ValueError("unknown POST route: " + path)
        return self.http_application(target_service).execute(
            match.action,
            payload or {},
            run_id=match.resource_id,
            template_id=match.template_id,
        )

    def raise_for(
        self,
        exc: Exception,
        *,
        not_found: bool = False,
        service_unavailable: bool = False,
    ) -> None:
        status, payload = error_projection(
            exc,
            not_found=not_found,
            service_unavailable=service_unavailable,
        )
        raise HTTPException(status_code=status, detail=payload) from exc

    @staticmethod
    def sse_line(event: Dict[str, Any]) -> str:
        """Encode one already-normalized RunEvent as an SSE message."""

        return "id: {}\nevent: run_event\ndata: {}\n\n".format(
            event["sequence"],
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        )

    async def event_stream(
        self,
        reader: HTTPApplication,
        run_id: str,
        *,
        after: int,
        limit: int,
        request: Request,
        sleep: Optional[Callable[[float], Awaitable[Any]]] = None,
    ) -> AsyncIterator[str]:
        """Replay persisted events and keep an SSE connection alive."""

        cursor = after
        sleep_fn = sleep or asyncio.sleep
        while True:
            if await request.is_disconnected():
                return
            payload = reader.read(
                "run_events",
                {"after": cursor, "limit": limit},
                resource_id=run_id,
            )
            events = payload.get("events") or []
            if events:
                for event in events:
                    yield self.sse_line(event)
                cursor = int(payload.get("next_cursor") or cursor)
                if page_contains_terminal_event(events):
                    return
                if payload.get("terminal") and not payload.get("has_more"):
                    return
                continue
            if payload.get("terminal"):
                return
            yield ": heartbeat\n\n"
            await sleep_fn(0.75)

    def event_stream_response(
        self,
        run_id: str,
        request: Request,
        *,
        after: Optional[int],
        limit: int,
        target_service: Any = None,
        sleep: Optional[Callable[[float], Awaitable[Any]]] = None,
    ) -> StreamingResponse:
        """Validate the stream request before opening a response body."""

        reader = self.http_application(target_service)
        cursor = validate_event_cursor(after)
        event_limit = validate_event_limit(limit)
        # A missing/foreign run must be returned as a normal JSON error rather
        # than being raised after the ASGI response has started.
        reader.read(
            "run_events",
            {"after": cursor, "limit": event_limit},
            resource_id=run_id,
        )
        return StreamingResponse(
            self.event_stream(
                reader,
                run_id,
                after=cursor,
                limit=event_limit,
                request=request,
                sleep=sleep,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def artifact_path(
        self,
        root: Path,
        name: str,
        suffix: str,
        prefix: str = "",
        *,
        domain_id: Optional[str] = None,
        metadata_root: Optional[Path] = None,
    ) -> Path:
        normalized_domain = str(domain_id or "").strip()[:80]
        if not normalized_domain:
            raise HTTPException(status_code=500, detail="artifact Domain is not bound")
        candidate = safe_artifact_path(
            root,
            name,
            suffix,
            prefix,
            domain_id=normalized_domain,
            metadata_root=metadata_root,
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return candidate

    def artifact_response(
        self,
        root: Path,
        name: str,
        suffix: str,
        content_type: str,
        *,
        prefix: str = "",
        domain_id: Optional[str] = None,
        metadata_root: Optional[Path] = None,
    ) -> FileResponse:
        return FileResponse(
            self.artifact_path(
                root,
                name,
                suffix,
                prefix,
                domain_id=domain_id,
                metadata_root=metadata_root,
            ),
            media_type=content_type,
        )

    @staticmethod
    def artifact_json(path: Path) -> Dict[str, Any]:
        try:
            return load_artifact_json(path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc

    def domain_artifact_path(
        self,
        domain_id: str,
        root: Path,
        name: str,
        suffix: str,
        prefix: str = "",
        *,
        metadata_root: Optional[Path] = None,
    ) -> Path:
        try:
            selection = self._deps()["host"].select(domain_id, source="explicit")
            return self.artifact_path(
                root,
                name,
                suffix,
                prefix,
                domain_id=selection.domain_id,
                metadata_root=metadata_root,
            )
        except HTTPException:
            raise
        except Exception as exc:
            self.raise_for(exc)
        raise AssertionError("raise_for must raise")

    def domain_artifact_response(
        self,
        domain_id: str,
        root: Path,
        name: str,
        suffix: str,
        content_type: str,
        *,
        prefix: str = "",
        metadata_root: Optional[Path] = None,
    ) -> FileResponse:
        return FileResponse(
            self.domain_artifact_path(
                domain_id,
                root,
                name,
                suffix,
                prefix,
                metadata_root=metadata_root,
            ),
            media_type=content_type,
        )


__all__ = ["FastAPIHttpAdapter"]
