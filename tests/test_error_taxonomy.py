"""Public contracts for bounded exception classification."""

from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from agent.error_taxonomy import classify_exception, normalize_failure_fields
from agent.errors import (
    AnswerUnavailable,
    ClarificationNeeded,
    PersistenceError,
    RequestRejected,
    RunCancelled,
    RunTimedOut,
    ToolError,
)
from agent.persistence.sqlite_retry import retry_sqlite_write
from agent.tool_provider import ToolProviderError


class ErrorTaxonomyTests(unittest.TestCase):
    def test_known_errors_keep_stable_fields(self):
        cases = (
            (
                ToolProviderError(
                    "private provider message",
                    provider_id="provider",
                    code="upstream_timeout",
                    retryable=True,
                ),
                {"category": "provider", "code": "upstream_timeout", "phase": "execution", "retryable": True},
            ),
            (
                ClarificationNeeded("missing input"),
                {"category": "clarification", "code": "clarification_required", "phase": "planning", "retryable": False},
            ),
            (
                RequestRejected("policy denied"),
                {"category": "policy", "code": "request_rejected", "phase": "planning", "retryable": False},
            ),
            (
                AnswerUnavailable("data is unavailable"),
                {"category": "data_unavailable", "code": "answer_unavailable", "phase": "answer", "retryable": False},
            ),
            (
                RunTimedOut("deadline"),
                {"category": "timeout", "code": "run_timeout", "phase": "control", "retryable": True},
            ),
            (
                RunCancelled("cancelled"),
                {"category": "cancelled", "code": "run_cancelled", "phase": "control", "retryable": False},
            ),
            (
                ToolError("schema rejected"),
                {"category": "tool", "code": "tool_error", "phase": "execution", "retryable": False},
            ),
        )
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(classify_exception(error), expected)

    def test_sqlite_lock_is_persistence_and_retryable(self):
        self.assertEqual(
            classify_exception(sqlite3.OperationalError("database is locked")),
            {
                "category": "persistence",
                "code": "sqlite_busy",
                "phase": "persistence",
                "retryable": True,
            },
        )

    def test_context_and_unknown_errors_are_bounded(self):
        self.assertEqual(
            classify_exception(ValueError("invalid request"), phase="transport"),
            {
                "category": "input",
                "code": "invalid_request",
                "phase": "transport",
                "retryable": False,
            },
        )
        classified = classify_exception(RuntimeError("private implementation detail"))
        self.assertEqual(classified["category"], "internal")
        self.assertEqual(classified["code"], "internal_error")
        self.assertEqual(classified["phase"], "execution")
        self.assertFalse(classified["retryable"])
        self.assertNotIn("private", str(classified))
    def test_retry_policy_replays_contention_and_normalizes_missing_retryability(self):
        calls = {"count": 0}

        @retry_sqlite_write
        def eventually_succeeds():
            calls["count"] += 1
            if calls["count"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        with patch("agent.persistence.sqlite_retry.time.sleep") as sleep:
            self.assertEqual(eventually_succeeds(), "ok")
        self.assertEqual(calls["count"], 3)
        self.assertEqual(sleep.call_count, 2)

        @retry_sqlite_write
        def always_busy():
            raise sqlite3.OperationalError("database is busy")

        with patch("agent.persistence.sqlite_retry.time.sleep"):
            with self.assertRaises(PersistenceError) as caught:
                always_busy()
        self.assertEqual(caught.exception.code, "sqlite_busy")
        self.assertEqual(
            normalize_failure_fields({"category": "provider"})["retryable"],
            True,
        )


if __name__ == "__main__":
    unittest.main()
