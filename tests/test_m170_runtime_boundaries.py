"""M170 production lifecycle and cross-domain persistence contracts."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import production_api
from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.text.domain import TEXT_DOMAIN_PACK


class M170RuntimeBoundaryTests(unittest.TestCase):
    def test_production_app_uses_lifespan_to_close_owned_service(self):
        original = production_api.service
        replacement = Mock()

        async def exercise_lifespan():
            async with production_api.app.router.lifespan_context(production_api.app):
                pass

        try:
            with patch.object(production_api, "service", replacement):
                asyncio.run(exercise_lifespan())
            replacement.close.assert_called_once_with()
            self.assertEqual(production_api.app.router.on_shutdown, [])
        finally:
            original.close()

    def test_text_artifact_domain_survives_read_and_domain_filter(self):
        with tempfile.TemporaryDirectory(prefix="m170-text-artifact-") as directory:
            store = ArtifactStore(Path(directory) / "runs")
            service = AgentService(
                artifact_store=store,
                domain_pack=TEXT_DOMAIN_PACK,
            )
            try:
                payload = service.run(
                    "请概括：跨领域 artifact 必须保留原始 Domain。",
                    planner="rule",
                    backend="memory",
                    session_id="m170-text-artifact",
                    export_artifact=True,
                )
                run_id = payload["run_id"]
            finally:
                service.close()

            restored = store.read_run(run_id, domain_id="text")
            hidden_from_gis = store.read_run(run_id, domain_id="gis")
            text_runs = store.list_runs(domain_id="text")
            gis_runs = store.list_runs(domain_id="gis")

        self.assertIsNotNone(restored)
        self.assertEqual(restored["domain_id"], "text")
        self.assertIsNone(hidden_from_gis)
        self.assertTrue(any(item.get("run_id") == run_id for item in text_runs))
        self.assertFalse(any(item.get("run_id") == run_id for item in gis_runs))


if __name__ == "__main__":
    unittest.main()
