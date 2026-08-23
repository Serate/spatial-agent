"""M225: compact offline persistence checks for Domain routing lineage."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.domain_registry import DomainEntry, DomainRegistry, DomainSelectionError
from agent.domain_routing_entry import DomainRoutingState
from agent.domain_selection import DomainSelection
from agent.domain_selector import DomainRoutingCandidate, DomainRoutingDecision
from agent.sqlite_store import SQLiteConversationStore


def _decision(
    decision_id: str,
    *,
    request: str = "查询洪山区边界",
    domain_id: str | None = "gis",
    parent_decision_id: str | None = None,
) -> DomainRoutingDecision:
    return DomainRoutingDecision(
        decision_id=decision_id,
        parent_decision_id=parent_decision_id,
        status="selected" if domain_id else "unmatched",
        reason_code="unique_match" if domain_id else "no_match",
        selector_id="test-selector",
        request_fingerprint=hashlib.sha256(request.encode("utf-8")).hexdigest(),
        candidates=(
            (
                DomainRoutingCandidate(
                    domain_id=domain_id,
                    label=domain_id.upper(),
                    score=100,
                    reasons=("test match",),
                ),
            )
            if domain_id
            else ()
        ),
        selection=(
            DomainSelection(domain_id=domain_id, source="automatic")
            if domain_id
            else None
        ),
    )


class M225DomainRoutingPersistenceTests(unittest.TestCase):
    def test_persistent_state_does_not_resurrect_cleared_process_cache(self):
        with tempfile.TemporaryDirectory(prefix="m225-authority-") as directory:
            store = SQLiteConversationStore(
                str(Path(directory) / "state.db"),
                domain_id="gis",
            )
            store.ensure_session("conversation-1")
            state = DomainRoutingState(store)
            decision = _decision("decision-cached")
            state.save(decision, "conversation-1")
            state.bind("conversation-1", "gis")

            store.clear_session("conversation-1")

            self.assertIsNone(state.get("decision-cached", "conversation-1"))
            self.assertEqual(state.bound_domain("conversation-1"), "gis")

            store.delete_session("conversation-1")

            self.assertIsNone(state.bound_domain("conversation-1"))

    def test_round_trip_and_restart_preserve_exact_selected_decision(self):
        with tempfile.TemporaryDirectory(prefix="m225-routing-") as directory:
            database = str(Path(directory) / "state.db")
            store = SQLiteConversationStore(database, domain_id="gis")
            decision = _decision("decision-root")

            saved = store.save_domain_routing_decision("conversation-1", decision)
            restored = SQLiteConversationStore(
                database, domain_id="gis"
            ).get_domain_routing_decision("decision-root", "conversation-1")

            self.assertEqual(restored, saved)
            self.assertEqual(restored["schema_version"], decision.schema_version)
            self.assertEqual(restored["domain_id"], "gis")
            self.assertEqual(restored["selection"], decision.to_dict()["selection"])
            self.assertIsInstance(restored["created_at"], float)

    def test_same_decision_is_idempotent_but_cannot_cross_sessions(self):
        with tempfile.TemporaryDirectory(prefix="m225-idempotent-") as directory:
            store = SQLiteConversationStore(str(Path(directory) / "state.db"))
            decision = _decision("decision-stable")
            store.ensure_session("conversation-1")

            first = store.save_domain_routing_decision("conversation-1", decision)
            with ThreadPoolExecutor(max_workers=4) as executor:
                repeated = list(
                    executor.map(
                        lambda _index: store.save_domain_routing_decision(
                            "conversation-1",
                            decision.to_dict(),
                        ),
                        range(8),
                    )
                )

            self.assertTrue(all(item == first for item in repeated))
            self.assertEqual(
                len(store.list_domain_routing_decisions("conversation-1")), 1
            )
            with self.assertRaises(ValueError):
                store.save_domain_routing_decision("conversation-2", decision)
            self.assertIsNone(
                store.get_domain_routing_decision(
                    "decision-stable", "conversation-2"
                )
            )
            self.assertTrue(store.delete_session("conversation-1"))
            self.assertIsNone(store.get_domain_routing_decision("decision-stable"))

    def test_lineage_limit_and_unmatched_decision_do_not_guess_domain(self):
        with tempfile.TemporaryDirectory(prefix="m225-lineage-") as directory:
            database = str(Path(directory) / "state.db")
            store = SQLiteConversationStore(database)
            root = _decision("decision-1", domain_id=None)
            child = _decision(
                "decision-2", parent_decision_id="decision-1", request="改用 GIS"
            )
            store.save_domain_routing_decision("conversation-1", root)
            store.save_domain_routing_decision("conversation-1", child)

            latest = store.list_domain_routing_decisions("conversation-1", limit=1)

            self.assertEqual([item["decision_id"] for item in latest], ["decision-2"])
            persisted_root = store.get_domain_routing_decision("decision-1")
            self.assertIsNone(persisted_root["domain_id"])
            self.assertIsNone(persisted_root["selection"])
            self.assertIsNone(store.get_bound_session_domain("conversation-1"))
            self.assertEqual(child.parent_decision_id, latest[0]["parent_decision_id"])

            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT decision_json, domain_id, parent_decision_id, "
                    "request_fingerprint, created_at FROM domain_routing_decisions "
                    "WHERE decision_id = 'decision-1'"
                ).fetchone()
            self.assertIn(root.schema_version, row[0])
            self.assertIsNone(row[1])
            self.assertEqual(row[3], root.request_fingerprint)
            self.assertGreater(row[4], 0)
            with self.assertRaisesRegex(ValueError, "parent.*does not exist"):
                store.save_domain_routing_decision(
                    "conversation-1",
                    _decision(
                        "decision-orphan",
                        parent_decision_id="decision-missing",
                    ),
                )
            unbound = _decision("decision-unbound", domain_id=None)
            store.save_domain_routing_decision("unbound-session", unbound)
            store.clear_session("unbound-session")
            self.assertEqual(
                store.list_domain_routing_decisions("unbound-session"),
                [],
            )
            store.save_domain_routing_decision("unbound-session", unbound)
            self.assertTrue(store.delete_session("unbound-session"))
            self.assertIsNone(store.get_domain_routing_decision("decision-unbound"))

    def test_bound_domain_lookup_is_read_only_and_survives_restart(self):
        with tempfile.TemporaryDirectory(prefix="m225-binding-") as directory:
            database = str(Path(directory) / "state.db")
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE session_domains "
                    "(session_id TEXT PRIMARY KEY, domain_id TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO session_domains VALUES (?, ?)",
                    ("conversation-text", "text"),
                )
            store = SQLiteConversationStore(database, domain_id="text")

            self.assertIsNone(store.get_bound_session_domain("conversation-missing"))
            self.assertEqual(store.get_bound_session_domain("conversation-text"), "text")

            rebuilt = SQLiteConversationStore(database, domain_id="gis")
            self.assertEqual(
                rebuilt.get_bound_session_domain("conversation-text"), "text"
            )
            self.assertIsNone(
                rebuilt.get_bound_session_domain("conversation-still-missing")
            )

            with self.assertRaises(DomainSelectionError):
                rebuilt.save_domain_routing_decision(
                    "conversation-text",
                    _decision("decision-wrong-domain", domain_id="gis"),
                )

    def test_custom_registry_and_corrupt_row_are_handled_at_persistence_seam(self):
        class FixturePack:
            domain_id = "fixture"

        registry = DomainRegistry(
            {
                "fixture": DomainEntry(
                    "fixture",
                    "Fixture",
                    "Fixture Domain",
                    FixturePack,
                )
            }
        )
        with tempfile.TemporaryDirectory(prefix="m225-registry-") as directory:
            database = str(Path(directory) / "state.db")
            store = SQLiteConversationStore(
                database,
                domain_id="fixture",
                legacy_domain_id="fixture",
                routing_registry=registry,
            )
            decision = _decision("decision-fixture", domain_id="fixture")
            store.save_domain_routing_decision("fixture-session", decision)
            self.assertEqual(
                store.get_domain_routing_decision("decision-fixture")["domain_id"],
                "fixture",
            )

            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE domain_routing_decisions SET request_fingerprint = ? "
                    "WHERE decision_id = ?",
                    ("0" * 64, "decision-fixture"),
                )
            with self.assertRaisesRegex(ValueError, "columns do not match"):
                store.get_domain_routing_decision("decision-fixture")


if __name__ == "__main__":
    unittest.main()
