import json
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.request_model import REQUEST_FACTS_SCHEMA_VERSION, parse_spatial_request
from agent.service import AgentService


COMPLEX_REQUEST = (
    "请对洪山区进行综合空间分析：查询行政区边界，统计DEM高程与坡度，"
    "分析土地利用分布，汇总道路和水体，并筛选坡度不超过20度、"
    "距离道路不超过1000米且排除水体的建设候选区域。"
)


class M95RequestFactsContractTests(unittest.TestCase):
    def test_request_facts_are_versioned_and_json_safe(self):
        facts = parse_spatial_request(COMPLEX_REQUEST)

        self.assertEqual(facts.as_dict()["schema_version"], REQUEST_FACTS_SCHEMA_VERSION)
        self.assertEqual(
            facts.as_context_dict()["schema_version"],
            REQUEST_FACTS_SCHEMA_VERSION,
        )
        self.assertNotIn("text", facts.as_context_dict())
        json.dumps(facts.as_dict(), ensure_ascii=False)

    def test_direct_preview_result_and_artifact_share_request_facts(self):
        expected = parse_spatial_request(COMPLEX_REQUEST).as_context_dict()
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(artifact_store=ArtifactStore(directory))
            preview = service.preview(COMPLEX_REQUEST)
            run = service.run(COMPLEX_REQUEST, export_artifact=True)
            artifact = json.loads(
                Path(run["artifact_ref"]).read_text(encoding="utf-8")
            )

        self.assertEqual(preview["request_facts"], expected)
        self.assertEqual(run["request_facts"], expected)
        self.assertEqual(run["result"]["request_facts"], expected)
        self.assertEqual(
            run["plan_evidence"]["execution_policy"]["schema_version"],
            "spatial-agent.execution-policy.v1",
        )
        self.assertTrue(run["plan_evidence"]["execution_policy"]["tools"])
        first_step_governance = run["steps"][0]["governance"]
        self.assertEqual(first_step_governance["permissions"], ["spatial_data:read"])
        self.assertEqual(
            run["result"]["data"]["evidence_steps"][0]["governance"],
            first_step_governance,
        )
        self.assertEqual(artifact["request_facts"], expected)
        self.assertEqual(artifact["result"]["request_facts"], expected)
        self.assertEqual(artifact["steps"][0]["governance"], first_step_governance)
        self.assertEqual(
            run["plan_evidence"]["request_facts"]["schema_version"],
            REQUEST_FACTS_SCHEMA_VERSION,
        )

    def test_sqlite_recovery_preserves_request_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            state_db = str(Path(directory) / "agent.db")
            first = AgentService(state_db_path=state_db).run(
                COMPLEX_REQUEST,
                session_id="request-facts-recovery",
            )
            restored = AgentService(state_db_path=state_db).get_run(first["run_id"])

        self.assertEqual(restored["request_facts"], first["request_facts"])
        self.assertEqual(
            restored["result"]["request_facts"],
            first["result"]["request_facts"],
        )


if __name__ == "__main__":
    unittest.main()
