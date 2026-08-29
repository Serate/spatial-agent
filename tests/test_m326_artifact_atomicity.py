"""Compact M326 regression for readable Artifact publication."""

from __future__ import annotations

import tempfile
import threading
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from agent.persistence.artifact_store import ArtifactStore
from scripts.live_http_acceptance import (
    AcceptanceFailure,
    _require_successful_live_model,
)


class M326ArtifactAtomicityTests(unittest.TestCase):
    def test_live_acceptance_rejects_provider_fallback(self):
        with self.assertRaisesRegex(AcceptanceFailure, "response_json_error"):
            _require_successful_live_model(
                {
                    "available": True,
                    "execution_mode": "live_model",
                    "status": "error",
                    "error_type": "response_json_error",
                },
                "async run",
            )
        _require_successful_live_model(
            {"available": True, "execution_mode": "live_model", "status": "success"},
            "async run",
        )

    def test_default_store_uses_the_configured_artifact_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SPATIAL_AGENT_ARTIFACT_ROOT": directory}):
                store = ArtifactStore()
            self.assertEqual(Path(directory), store._root)

    def test_reader_never_sees_a_half_written_run_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(str(root))
            initial = {
                "run_id": "m326-atomic",
                "domain_id": "gis",
                "status": "COMPLETED",
                "answer": "旧版本",
                "result": {"type": "text_result", "answer": "旧版本"},
            }
            updated = {**initial, "answer": "新版本"}
            store.write_run(initial)

            started = threading.Event()
            release = threading.Event()
            original_write_text = Path.write_text
            first_write = True

            def slow_write_text(path, data, *args, **kwargs):
                nonlocal first_write
                if first_write:
                    first_write = False
                    original_write_text(path, data[:1], *args, **kwargs)
                    started.set()
                    if not release.wait(2):
                        raise AssertionError("test writer was not released")
                    return original_write_text(path, data, *args, **kwargs)
                return original_write_text(path, data, *args, **kwargs)

            with patch.object(Path, "write_text", new=slow_write_text):
                writer = threading.Thread(target=store.write_run, args=(updated,))
                writer.start()
                self.assertTrue(started.wait(2))
                observed = store.read_run("m326-atomic", domain_id="gis")
                release.set()
                writer.join(2)

            self.assertFalse(writer.is_alive())
            self.assertIsNotNone(observed)
            self.assertEqual("旧版本", observed["answer"])
            self.assertEqual("新版本", store.read_run("m326-atomic")["answer"])


if __name__ == "__main__":
    unittest.main()
