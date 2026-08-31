"""Compatibility facade for the canonical AgentService application boundary.

The implementation lives in ``agent.application.service_facade``.  This
module keeps the historical import and patch seams stable while new callers
should depend on the application package directly.
"""

from agent.application.service_facade import AgentService
from agent.application.service_async import process_is_alive as _process_is_alive
from agent.application.service_format import (
    analysis_ready_summary as _analysis_ready_summary,
    exported_geometry_evidence as _exported_geometry_evidence,
    normalize_spatial_context as _normalize_spatial_context,
    tag_geometry_features as _tag_geometry_features,
)
from agent.application.service_sessions import (
    dedupe_run_records as _dedupe_run_records,
    validate_session_id as _validate_session_id,
)
from agent.geojson_exporter import export_run_summary
from agent.runtime_factory import (
    build_general_runtime,
    build_general_runtime_context_snapshot,
    build_runtime,
    build_runtime_context_snapshot,
)

__all__ = [
    "AgentService",
    "export_run_summary",
    "_analysis_ready_summary",
    "_exported_geometry_evidence",
    "_normalize_spatial_context",
    "_tag_geometry_features",
    "_dedupe_run_records",
    "_validate_session_id",
    "build_general_runtime",
    "build_general_runtime_context_snapshot",
    "build_runtime",
    "build_runtime_context_snapshot",
]
