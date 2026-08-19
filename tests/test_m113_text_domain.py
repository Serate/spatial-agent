import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.errors import ToolError
from agent.service import AgentService
from evaluation.contract_harness import compare_results
from domains.text.runtime import build_text_runtime


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


class M113TextDomainTests(unittest.TestCase):
    def test_non_gis_tool_runs_through_registry_and_runtime(self):
        runtime = build_text_runtime()

        result = runtime.run("这是一段需要被摘要的文本。")

        self.assertEqual(runtime._allowed_permissions, {"text_data:read"})
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "text_summary_result")
        self.assertEqual(result.steps[0].tool, "summarize_text")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[0].result["word_count"], 1)
        self.assertIn("文本摘要：", result.answer)
        self.assertEqual(
            result.context_evidence["section_names"].count("capability_catalog"),
            1,
        )
        self.assertEqual(
            result.plan_evidence["selected_capability_id"], "text_summary"
        )

    def test_text_tool_schema_rejects_unknown_input(self):
        runtime = build_text_runtime()

        with self.assertRaises(ToolError):
            runtime._registry.invoke(
                "summarize_text",
                {"text": "摘要", "unexpected": True},
            )

    def test_service_and_artifact_share_non_gis_result_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory,
            )
            try:
                payload = service.run(
                    "请摘要这段文本并保留可审计的执行证据。",
                    export_artifact=True,
                )
            finally:
                service.close()

            artifact_path = Path(payload["artifact_ref"])
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["result"]["type"], "text_summary_result")
        self.assertEqual(payload["result"]["title"], "文本摘要")
        self.assertTrue(payload["result"]["workspace"]["registered_type"])
        self.assertIn("generic", payload["result"]["workspace"]["panels"])
        self.assertEqual(payload["result"]["planning"]["domain_id"], "text")
        self.assertEqual(compare_results([payload, artifact]), [])
        self.assertEqual(
            artifact["result"]["data"]["evidence_steps"][0]["tool"],
            "summarize_text",
        )


if __name__ == "__main__":
    unittest.main()
