"""M171 explicit legacy-domain adapter contracts."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.models import AgentRunResult, RunStatus
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore


class M171DomainDefaultTests(unittest.TestCase):
    def test_console_bootstrap_ready_does_not_wait_for_history_render(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        reload_domain = source.split(
            "async function reloadDomainContext()", 1
        )[1].split("function workflowFieldId", 1)[0]
        self.assertLess(
            reload_domain.index("window.__consoleDomainReady=true"),
            reload_domain.index("restoreSession(domainId)"),
        )

    def test_legacy_artifact_domain_is_configurable_without_gis_fallback(self):
        with tempfile.TemporaryDirectory(prefix="m171-legacy-domain-") as directory:
            root = Path(directory)
            (root / "legacy-text.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy-text",
                        "status": "COMPLETED",
                        "request": "概括一段文本",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = ArtifactStore(root, legacy_domain_id="text")
            restored = store.read_run("legacy-text", domain_id="text")
            hidden_from_gis = store.read_run("legacy-text", domain_id="gis")
            text_runs = store.list_runs(domain_id="text")
            gis_runs = store.list_runs(domain_id="gis")

        self.assertIsNotNone(restored)
        self.assertIsNone(hidden_from_gis)
        self.assertEqual(text_runs[0]["domain_id"], "text")
        self.assertEqual(gis_runs, [])

    def test_legacy_domain_id_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="m171-domain-validation-") as directory:
            with self.assertRaises(ValueError):
                ArtifactStore(directory, legacy_domain_id=" ")
            with self.assertRaises(ValueError):
                ArtifactStore(directory, legacy_domain_id="x" * 81)
            with self.assertRaises(ValueError):
                SQLiteStateStore(
                    str(Path(directory) / "runs.db"),
                    legacy_domain_id="x" * 81,
                )

    def test_sqlite_legacy_snapshot_uses_selected_domain_for_reads_and_restore(self):
        with tempfile.TemporaryDirectory(prefix="m171-sqlite-domain-") as directory:
            path = str(Path(directory) / "runs.db")
            writer = SQLiteStateStore(path, legacy_domain_id="text")
            writer.save(
                AgentRunResult(
                    run_id="legacy-text-run",
                    status=RunStatus.COMPLETED,
                    request="概括一段文本",
                )
            )

            text_store = SQLiteStateStore(path, legacy_domain_id="text")
            restored = text_store.get("legacy-text-run", domain_id="text")
            text_runs = text_store.list_runs(domain_id="text")
            hidden_from_gis = text_store.get("legacy-text-run", domain_id="gis")

        self.assertIsNotNone(restored)
        self.assertEqual(restored.domain_id, "text")
        self.assertEqual(text_runs[0]["domain_id"], "text")
        self.assertIsNone(hidden_from_gis)

    def test_sqlite_legacy_async_payload_uses_selected_domain(self):
        with tempfile.TemporaryDirectory(prefix="m171-async-domain-") as directory:
            path = str(Path(directory) / "runs.db")
            store = SQLiteStateStore(path, legacy_domain_id="text")
            store.create_async_job(
                "legacy-text-key",
                "legacy-text-job",
                {"request": "概括一段文本", "session_id": "m171-text"},
            )

            restored = store.get_async_job("legacy-text-job", domain_id="text")
            hidden_from_gis = store.get_async_job(
                "legacy-text-job", domain_id="gis"
            )

        self.assertEqual(restored["payload"]["domain_id"], "text")
        self.assertIsNone(hidden_from_gis)

    def test_service_passes_selected_domain_to_implicit_persistence_adapters(self):
        with tempfile.TemporaryDirectory(prefix="m171-service-domain-") as directory:
            service = AgentService(
                state_db_path=str(Path(directory) / "runs.db"),
                domain_id="text",
            )
            try:
                self.assertEqual(service._state_store._legacy_domain_id, "text")
                self.assertEqual(service._artifact_store._legacy_domain_id, "text")
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
