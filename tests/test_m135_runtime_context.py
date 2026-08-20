import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.contract_versions import (
    RESULT_ENVELOPE_SCHEMA_VERSION,
    TASK_PLAN_SCHEMA_VERSION,
)
from agent.runtime_context import (
    RUNTIME_CONTEXT_SCHEMA_VERSION,
    RuntimeContextMismatchError,
    assert_runtime_context_compatible,
    build_runtime_context,
    normalize_runtime_context,
    runtime_context_fingerprint,
)
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.service import AgentService
from result_contract import build_result_contract


class M135RuntimeContextTests(unittest.TestCase):
    def test_runtime_context_binds_replaceable_components(self):
        runtime = build_runtime("rule", "memory", domain_id="text")
        context = runtime.runtime_context()
        result = runtime.run("请摘要这段文本。")

        self.assertEqual(context["schema_version"], RUNTIME_CONTEXT_SCHEMA_VERSION)
        self.assertEqual(context["domain_id"], "text")
        self.assertEqual(context["planner"], "rule")
        self.assertEqual(context["backend"], "memory")
        self.assertEqual(context["tool_provider"]["id"], "text-native")
        self.assertEqual(
            context["contracts"]["task_plan"], TASK_PLAN_SCHEMA_VERSION
        )
        self.assertEqual(
            context["contracts"]["result_envelope"], RESULT_ENVELOPE_SCHEMA_VERSION
        )
        self.assertEqual(result.to_dict()["runtime_context"], context)
        self.assertNotIn("请摘要", json.dumps(context, ensure_ascii=False))

        envelope = build_result_contract(
            {**result.to_dict(), "result_type": result.plan.output["type"]},
            registry=runtime.result_registry(),
        )
        self.assertEqual(envelope["schema_version"], RESULT_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(envelope["runtime_context"], context)

    def test_runtime_capability_snapshot_exposes_the_same_context(self):
        runtime = build_runtime("rule", "memory", domain_id="text")

        snapshot = runtime.runtime_capabilities(max_files=1)

        self.assertEqual(snapshot["runtime_context"], runtime.runtime_context())
        self.assertEqual(snapshot["runtime_context"]["domain_id"], "text")

    def test_sqlite_and_artifact_recovery_preserve_context_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "agent.db")
            service = AgentService(
                state_db_path=database,
                artifact_store=ArtifactStore(str(Path(directory) / "runs")),
                domain_id="text",
            )
            try:
                payload = service.run(
                    "请摘要这段文本并保留运行上下文。",
                    export_artifact=True,
                )
                expected = payload["runtime_context"]
                self.assertEqual(
                    payload["provenance"]["runtime_context_fingerprint"],
                    expected["fingerprint"],
                )
                self.assertEqual(
                    payload["result"]["model_evidence"]["context_fingerprint"],
                    expected["fingerprint"],
                )
                self.assertEqual(
                    payload["result"]["deployment_evidence"]["context_fingerprint"],
                    expected["fingerprint"],
                )
                artifact = json.loads(
                    Path(payload["artifact_ref"]).read_text(encoding="utf-8")
                )
            finally:
                service.close()

            restored_service = AgentService(
                state_db_path=database,
                artifact_store=ArtifactStore(str(Path(directory) / "runs")),
                domain_id="text",
            )
            try:
                restored = restored_service.get_run(payload["run_id"])
            finally:
                restored_service.close()

        self.assertEqual(artifact["runtime_context"], expected)
        self.assertEqual(restored["runtime_context"], expected)

    def test_async_submission_persists_context_before_worker_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                state_db_path=str(Path(directory) / "agent.db"),
                domain_id="text",
            )
            try:
                submitted = service.run_async(
                    request="请摘要异步文本。",
                    session_id="m135-async",
                )
                job = service._state_store.get_async_job(submitted["run_id"])
            finally:
                service.close()

        self.assertEqual(
            job["payload"]["runtime_context"]["schema_version"],
            RUNTIME_CONTEXT_SCHEMA_VERSION,
        )
        self.assertEqual(job["payload"]["runtime_context"]["domain_id"], "text")

    def test_context_normalization_is_bounded_and_json_safe(self):
        value = build_runtime_context(
            domain_id="text",
            planner="rule",
            backend="memory",
            permissions=["b", "a", "a"],
            tool_provider={"id": "text-native", "tool_count": "bad"},
        )
        normalized = normalize_runtime_context(value)

        self.assertEqual(normalized["permissions"], ["a", "b"])
        self.assertEqual(normalized["tool_provider"]["tool_count"], 0)
        self.assertTrue(normalized["fingerprint"].startswith("sha256:"))
        self.assertEqual(runtime_context_fingerprint(normalized), normalized["fingerprint"])
        json.dumps(normalized, ensure_ascii=False)

    def test_context_drift_is_rejected_before_async_execution(self):
        expected = build_runtime("rule", "memory", domain_id="text").runtime_context()
        actual = dict(expected)
        actual["backend"] = "local"

        with self.assertRaises(RuntimeContextMismatchError):
            assert_runtime_context_compatible(expected, actual)

    def test_model_evidence_is_allowlisted_and_binds_context(self):
        context = build_runtime("rule", "memory", domain_id="text").runtime_context()
        unsafe_context = dict(context)
        unsafe_context["api_key"] = "sk-never-return-this"
        unsafe_context["private_path"] = "D:/private/provider.json"
        contract = build_result_contract(
            {
                "result_type": "text_summary_result",
                "runtime_context": unsafe_context,
                "planner_metrics": {
                    "provider": "openai-compatible",
                    "model": "demo-model",
                    "wire_api": "responses",
                    "status": "success",
                    "attempts": 2,
                    "retries": 1,
                    "latency_ms": 12.34567,
                    "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
                    "raw_response": "private provider response",
                    "api_key": "sk-never-return-this",
                    "private_path": "D:/private/provider.json",
                },
            }
        )

        evidence = contract["model_evidence"]
        self.assertEqual(evidence["context_fingerprint"], context["fingerprint"])
        self.assertEqual(evidence["execution_mode"], "rule")
        self.assertEqual(evidence["usage"]["total_tokens"], 14)
        self.assertEqual(contract["runtime_context"], context)
        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("private provider response", encoded)
        self.assertNotIn("sk-never-return-this", encoded)
        self.assertNotIn("private_path", encoded)

    def test_submission_snapshot_does_not_initialize_gis_backend(self):
        with patch(
            "domains.gis.domain.GisDomainPack.tool_provider",
            side_effect=AssertionError("backend must stay deferred"),
        ):
            snapshot = build_runtime_context_snapshot(
                "rule", "local", domain_id="gis"
            )

        self.assertEqual(snapshot["domain_id"], "gis")
        self.assertEqual(snapshot["tool_provider"]["id"], "native")

    def test_console_renders_runtime_context_alongside_execution_record(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("runtime_context", source)
        self.assertIn("context.tool_provider", source)
        self.assertIn("context.domain_id", source)
        self.assertIn("deployment_evidence", source)
        self.assertIn("deployment.data", source)
        self.assertIn("发布证据", source)
        self.assertIn("Planner ", source)


if __name__ == "__main__":
    unittest.main()
