"""Shared SQLite connection + async-job row helpers for the persistence adapters.

Split out of ``sqlite_store`` so both the state and conversation stores can share
the connection and row-projection seams without a circular import.
"""

"""SQLite-backed state and conversation stores for the production demo."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..errors import PersistenceError
from .sqlite_retry import (
    is_sqlite_contention as _is_sqlite_contention,
    retry_sqlite_write as _retry_sqlite_write,
)
from ..models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from ..conversation_turn import normalize_conversation_turn
from ..domain_registry import DomainRegistry, DomainSelectionError, domain_registry
from ..domain_selector import resolve_domain_routing_decision
from ..runtime_context import normalize_runtime_context
from ..runtime_state import PendingClarification
from ..evidence_registry import normalize_evidence_registry
from ..recovery_action import normalize_action_receipt
from ..execution_timeline import normalize_execution_timeline
from ..nested_schema import normalize_domain_routing_evidence_contract
from ..interaction_contract import InteractionContractError
from ..run_events import normalize_run_event, validate_event_cursor, validate_event_limit
from ..request_mode import normalize_request_mode

def _connect_sqlite(path: Path) -> sqlite3.Connection:
    """Open SQLite with a retry for concurrent WAL mode initialization."""
    for attempt in range(6):
        connection = sqlite3.connect(str(path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except sqlite3.OperationalError as exc:
            connection.close()
            if "locked" not in str(exc).lower() or attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise RuntimeError("SQLite connection retry exhausted")

_ROUTING_INTERACTION_RECEIPT_SELECT = """
    SELECT subject_decision_id, action, idempotency_key, input_fingerprint,
           status, result_decision_id, error_code, created_at, updated_at
      FROM domain_routing_interaction_receipts
"""


def _routing_interaction_receipt_from_row(
    row: Any,
    *,
    reused: bool,
) -> Dict[str, Any]:
    if row is None:
        raise ValueError("routing interaction receipt is missing")
    return normalize_action_receipt(
        {
            "status": row[4],
            "action_id": row[1],
            "subject": {"kind": "routing_decision", "id": row[0]},
            "result_ref": {"kind": "routing_decision", "id": row[5]},
            "idempotency_key": row[2],
            "input_fingerprint": row[3],
            "error_code": row[6],
            "reused": reused,
        }
    )
