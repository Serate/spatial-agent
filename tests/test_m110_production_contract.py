import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService


ROOT = Path(__file__).resolve().parents[1]


def _payload(answer="完成"):
    return {
        "status": "COMPLETED",
        "answer": answer,
        "steps": [{"tool": "range_query", "status": "COMPLETED", "governance": {"timeout": 10}}],
        "trace_summary": ["one"],
        "context_evidence": {"section_names": ["capability_catalog"]},
        "result": {
            "type": "admin_area_result",
            "planning": {
                "source": "rule",
                "plan_identity": {"version": "spatial-agent.plan-identity.v1"},
                "selected_capability_id": "admin_boundary_query",
                "capability_candidate_ids": ["admin_boundary_query"],
                "capability_catalog_available": True,
                "capability_catalog_ids": ["admin_boundary_query"],
                "execution_policy": {"mode": "safe"},
                "capability_catalog_environment": "memory",
                "capability_catalog_tool_schema_count": 1,
                "exact_template_ids": ["admin_boundary_query"],
                "matched_template_ids": ["admin_boundary_query"],
            },
            "lineage": {"artifact": {"available": True}},
            "workspace": {"panels": ["answer", "steps"]},
            "views": {
                "schema_version": "spatial-agent.views.v1",
                "panels": {"steps": {"kind": "steps"}},
            },
        },
    }


class M110ProductionContractTests(unittest.TestCase):
    def _run_checker(self, payloads):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payloads.json"
            path.write_text(json.dumps(payloads, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "contract_harness_check.py"),
                    "--input",
                    str(path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

    def test_checker_reuses_harness_for_equivalent_entries(self):
        completed = self._run_checker([_payload(), _payload()])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "ok")

    def test_checker_reports_contract_mismatch(self):
        completed = self._run_checker([_payload(), _payload("不同答案")])
        self.assertEqual(completed.returncode, 1)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "mismatch")
        self.assertIn("$.answer", report["differences"][0])

    def test_checker_accepts_real_service_and_artifact_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(artifact_store=ArtifactStore(directory))
            result = service.run("查询洪山区行政区边界", export_artifact=True)
            artifact = json.loads(Path(result["artifact_ref"]).read_text(encoding="utf-8"))
            completed = self._run_checker([result, artifact])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "ok")

    def test_production_acceptance_calls_shared_checker(self):
        source = (ROOT / "scripts" / "production_acceptance.ps1").read_text(encoding="utf-8")
        self.assertIn("function Invoke-ContractHarness", source)
        self.assertIn("contract_harness_check.py", source)
        self.assertIn("syncArtifactContract", source)

    def test_production_acceptance_resolves_real_python_and_reports_harness_exit(self):
        source = (ROOT / "scripts" / "production_acceptance.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("function Resolve-ContractHarnessPython", source)
        self.assertIn("WindowsApps", source)
        self.assertIn("SPATIAL_AGENT_PYTHON", source)
        self.assertIn("contract harness failed (python=", source)
        self.assertIn("exit_code=", source)


if __name__ == "__main__":
    unittest.main()
