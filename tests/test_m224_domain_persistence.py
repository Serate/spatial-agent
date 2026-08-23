"""M224-C: persistent Domain isolation for sessions and async identity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Callable

from agent.artifact_store import ArtifactStore
from agent.domain_registry import DomainSelectionError
from agent.domain_runtime_host import DomainRuntimeHost
from agent.models import AgentRunResult, RunStatus
from agent.service import AgentService
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore


class M224DomainPersistenceTests(unittest.TestCase):
    def _host(self, root: Path) -> DomainRuntimeHost:
        database = str(root / "state.db")

        def build_service(domain_id: str) -> AgentService:
            return AgentService(
                artifact_store=ArtifactStore(root / "artifacts" / domain_id),
                state_db_path=database,
                domain_id=domain_id,
            )

        return DomainRuntimeHost(service_factory=build_service)

    def _assert_session_domain_mismatch(self, operation: Callable[[], object]) -> None:
        try:
            operation()
        except Exception as exc:
            self.assertEqual(
                getattr(exc, "code", None),
                "session_domain_mismatch",
                "cross-Domain session access must expose a stable error code",
            )
            self.assertTrue(
                isinstance(exc, DomainSelectionError)
                or exc.__class__.__name__.endswith("DomainSelectionError")
            )
            return
        self.fail("cross-Domain session access was not rejected")

    def test_explicit_async_idempotency_key_is_scoped_by_domain(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-async-") as directory:
            with self._host(Path(directory)) as host:
                gis = host.service("gis").run_async(
                    request="查询DEM栅格元数据",
                    session_id="conversation-gis-async",
                    idempotency_key="shared-explicit-key",
                )
                text = host.service("text").run_async(
                    request="请摘要这段文本。",
                    session_id="conversation-text-async",
                    idempotency_key="shared-explicit-key",
                )

                self.assertFalse(gis["idempotent"])
                self.assertFalse(text["idempotent"])
                self.assertNotEqual(gis["run_id"], text["run_id"])

    def test_bound_session_rejects_cross_domain_run_pending_read_and_clear(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-binding-") as directory:
            with self._host(Path(directory)) as host:
                gis = host.service("gis")
                text = host.service("text")

                run_session = "conversation-gis-run-owner"
                gis.run("查询DEM栅格元数据", session_id=run_session)
                self._assert_session_domain_mismatch(
                    lambda: text.run("请摘要这段文本。", session_id=run_session)
                )

                pending_session = "conversation-gis-pending-owner"
                pending = gis.run("查询行政区边界", session_id=pending_session)
                self.assertEqual(pending["status"], "NEEDS_CLARIFICATION")
                self._assert_session_domain_mismatch(
                    lambda: text.preview("请摘要这段文本。", session_id=pending_session)
                )

                clear_session = "conversation-gis-clear-owner"
                gis.run("查询DEM栅格元数据", session_id=clear_session)
                self._assert_session_domain_mismatch(
                    lambda: text.clear_session(clear_session)
                )

    def test_list_sessions_only_returns_sessions_bound_to_service_domain(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-list-") as directory:
            with self._host(Path(directory)) as host:
                gis = host.service("gis")
                text = host.service("text")
                gis.run("查询DEM栅格元数据", session_id="conversation-gis-only")
                text.run("请摘要这段文本。", session_id="conversation-text-only")

                gis_sessions = {
                    item["session_id"] for item in gis.list_sessions()["sessions"]
                }
                text_sessions = {
                    item["session_id"] for item in text.list_sessions()["sessions"]
                }

                self.assertEqual(gis_sessions, {"conversation-gis-only"})
                self.assertEqual(text_sessions, {"conversation-text-only"})

    def test_clear_session_removes_only_own_domain_runs_and_async_jobs(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-clear-") as directory:
            root = Path(directory)
            with self._host(root) as host:
                gis = host.service("gis")
                text = host.service("text")
                session_id = "conversation-shared-legacy-records"
                gis_result = gis.run("查询DEM栅格元数据", session_id=session_id)

                store = SQLiteStateStore(str(root / "state.db"))
                store.save(
                    AgentRunResult(
                        run_id="text-legacy-run",
                        status=RunStatus.COMPLETED,
                        request="请摘要这段文本。",
                        session_id=session_id,
                        domain_id="text",
                        answer="摘要完成。",
                    )
                )
                store.create_async_job(
                    "gis-clear-key",
                    "gis-clear-job",
                    {
                        "request": "查询DEM栅格元数据",
                        "session_id": session_id,
                        "domain_id": "gis",
                    },
                )
                store.create_async_job(
                    "text-preserve-key",
                    "text-preserve-job",
                    {
                        "request": "请摘要这段文本。",
                        "session_id": session_id,
                        "domain_id": "text",
                    },
                )

                cleared = gis.clear_session(session_id)

                self.assertEqual(cleared["cleared_runs"], 1)
                with self.assertRaises(ValueError):
                    gis.get_run(gis_result["run_id"])
                self.assertEqual(text.get_run("text-legacy-run")["domain_id"], "text")
                with self.assertRaises(ValueError):
                    gis.get_async_observability("gis-clear-job")
                self.assertEqual(
                    text.get_async_observability("text-preserve-job")["run_id"],
                    "text-preserve-job",
                )

    def test_rebuilt_host_reads_each_domains_own_persisted_records(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-rebuild-") as directory:
            root = Path(directory)
            with self._host(root) as first_host:
                gis_result = first_host.service("gis").run(
                    "查询DEM栅格元数据",
                    session_id="conversation-gis-rebuilt",
                )
                text_result = first_host.service("text").run(
                    "请摘要这段文本。",
                    session_id="conversation-text-rebuilt",
                )

            with self._host(root) as rebuilt_host:
                gis = rebuilt_host.service("gis")
                text = rebuilt_host.service("text")

                self.assertEqual(gis.get_run(gis_result["run_id"])["domain_id"], "gis")
                self.assertEqual(
                    text.get_run(text_result["run_id"])["domain_id"], "text"
                )
                with self.assertRaises(ValueError):
                    gis.get_run(text_result["run_id"])
                with self.assertRaises(ValueError):
                    text.get_run(gis_result["run_id"])
                self.assertEqual(
                    {item["session_id"] for item in gis.list_sessions()["sessions"]},
                    {"conversation-gis-rebuilt"},
                )
                self.assertEqual(
                    {item["session_id"] for item in text.list_sessions()["sessions"]},
                    {"conversation-text-rebuilt"},
                )

    def test_unbound_legacy_session_migrates_to_default_gis_domain(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-legacy-") as directory:
            root = Path(directory)
            legacy = SQLiteConversationStore(str(root / "state.db"))
            legacy.save_pending(
                "conversation-legacy-unbound",
                "查询行政区边界",
                "admin name is required",
            )

            with self._host(root) as host:
                gis = host.service("gis")
                text = host.service("text")

                self.assertNotIn(
                    "conversation-legacy-unbound",
                    {item["session_id"] for item in text.list_sessions()["sessions"]},
                )
                migrated = gis.run("洪山区", session_id="conversation-legacy-unbound")
                self.assertEqual(migrated["domain_id"], "gis")
                self.assertIn(
                    "conversation-legacy-unbound",
                    {item["session_id"] for item in gis.list_sessions()["sessions"]},
                )
                self._assert_session_domain_mismatch(
                    lambda: text.preview(
                        "请摘要这段文本。",
                        session_id="conversation-legacy-unbound",
                    )
                )


if __name__ == "__main__":
    unittest.main()
