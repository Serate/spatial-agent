"""M149 shared nested result schema migration and recovery boundary."""

import unittest
import json
import tempfile
from pathlib import Path

from agent.nested_schema import (
    NestedSchemaError,
    normalize_result_contract,
    normalize_views,
    unavailable_nested_view,
)
from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from agent.service_async import normalize_async_result_evidence
from result_contract import build_result_contract


class M149NestedSchemaTests(unittest.TestCase):
    def test_legacy_missing_nested_versions_are_migrated(self):
        result = normalize_result_contract(
            {
                "type": "text_summary_result",
                "workspace": {
                    "panels": ["generic"],
                    "view_specs": [{"id": "generic", "renderer": "generic"}],
                },
                "views": {
                    "panels": {"generic": {"kind": "text_summary"}},
                },
            }
        )

        self.assertEqual(result["schema_version"], "spatial-agent.result-envelope.v1")
        self.assertEqual(result["workspace"]["schema_version"], "spatial-agent.workspace.v1")
        self.assertEqual(result["views"]["schema_version"], "spatial-agent.views.v1")
        self.assertEqual(
            result["views"]["panels"]["generic"]["schema_version"],
            "spatial-agent.view.v1",
        )

    def test_unknown_nested_version_is_not_silently_accepted(self):
        with self.assertRaises(NestedSchemaError) as captured:
            normalize_result_contract(
                {
                    "type": "x",
                    "workspace": {"schema_version": "spatial-agent.workspace.v9"},
                    "views": {"panels": {}},
                }
            )
        self.assertEqual(captured.exception.reason_code, "nested_schema_unknown_version")
        self.assertIn("workspace.schema_version", captured.exception.path)

        with self.assertRaises(NestedSchemaError):
            normalize_views(
                {
                    "schema_version": "spatial-agent.views.v1",
                    "panels": {
                        "future": {
                            "schema_version": "spatial-agent.view.v9",
                            "kind": "future",
                        }
                    },
                }
            )

    def test_runtime_result_stamps_panel_version(self):
        result = build_result_contract(
            {
                "result_type": "text_summary_result",
                "answer": "完成",
                "steps": [
                    {
                        "id": "summary",
                        "tool": "summarize_text",
                        "status": "COMPLETED",
                        "result": {"summary": "完成", "char_count": 2, "word_count": 1},
                    }
                ],
            }
        )
        self.assertEqual(
            result["views"]["panels"]["generic"]["schema_version"],
            "spatial-agent.view.v1",
        )

    def test_recovery_fallback_contains_no_future_panel_fields(self):
        fallback = unavailable_nested_view(
            result_type="future_result", reason_code="nested_schema_unknown_version"
        )
        panel = fallback["views"]["panels"]["generic"]
        self.assertEqual(panel["kind"], "unavailable")
        self.assertEqual(panel["state"], "unavailable")
        self.assertNotIn("raw_panel", panel)

    def test_artifact_recovery_does_not_copy_unknown_nested_views(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "future.json").write_text(
                json.dumps(
                    {
                        "artifact_schema_version": "spatial-agent.run-artifact.v1",
                        "run_id": "future",
                        "status": "COMPLETED",
                        "domain_id": "gis",
                        "result": {
                            "schema_version": "spatial-agent.result-envelope.v1",
                            "type": "future_result",
                            "workspace": {"schema_version": "spatial-agent.workspace.v9"},
                            "views": {"schema_version": "spatial-agent.views.v1", "panels": {}},
                        },
                    }
                ),
                encoding="utf-8",
            )
            service = AgentService(artifact_store=ArtifactStore(root))
            try:
                payload = service.get_run("future")
            finally:
                service.close()
        panel = payload["result"]["views"]["panels"]["generic"]
        self.assertEqual(panel["kind"], "unavailable")
        self.assertEqual(
            payload["result"]["schema_warnings"][0]["reason_code"],
            "nested_schema_unknown_version",
        )

    def test_async_unknown_nested_panel_becomes_unavailable(self):
        evidence = normalize_async_result_evidence(
            {
                "schema_version": "spatial-agent.async-result-evidence.v1",
                "state": "success",
                "workspace": {"schema_version": "spatial-agent.workspace.v1", "panels": []},
                "views": {
                    "schema_version": "spatial-agent.views.v1",
                    "panels": {
                        "future": {
                            "schema_version": "spatial-agent.view.v9",
                            "kind": "future",
                        }
                    },
                },
            }
        )
        self.assertEqual(evidence["state"], "unavailable")
        self.assertEqual(evidence["reason_code"], "nested_schema_unknown_version")


if __name__ == "__main__":
    unittest.main()
