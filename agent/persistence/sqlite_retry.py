"""Bounded retry policy shared by every SQLite persistence adapter."""

from __future__ import annotations

from functools import wraps
import sqlite3
import time
from typing import Any, Callable

from agent.errors import PersistenceError


SQLITE_RETRY_ATTEMPTS = 4
SQLITE_RETRY_BASE_SECONDS = 0.02


def is_sqlite_contention(exc: BaseException) -> bool:
    """Recognize transient SQLite lock contention, not malformed SQL."""

    text = str(exc).lower()
    return any(
        token in text
        for token in ("locked", "busy", "cannot start a transaction")
    )


def retry_sqlite_write(function: Callable[..., Any]) -> Callable[..., Any]:
    """Replay one bounded write operation after transient contention."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        for attempt in range(SQLITE_RETRY_ATTEMPTS):
            try:
                return function(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                if not is_sqlite_contention(exc):
                    raise
                if attempt == SQLITE_RETRY_ATTEMPTS - 1:
                    raise PersistenceError(
                        "durable state is busy",
                        code="sqlite_busy",
                        retryable=True,
                    ) from exc
                time.sleep(SQLITE_RETRY_BASE_SECONDS * (2**attempt))
        raise PersistenceError(
            "durable state write retry exhausted",
            code="sqlite_busy",
            retryable=True,
        )

    return wrapped


__all__ = [
    "SQLITE_RETRY_ATTEMPTS",
    "SQLITE_RETRY_BASE_SECONDS",
    "is_sqlite_contention",
    "retry_sqlite_write",
]
