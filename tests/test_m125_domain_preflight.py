"""M125 domain-owned preflight seam and public Runtime decoupling contracts."""

import unittest
from pathlib import Path

from agent.domain_contract import preflight_tool


ROOT = Path(__file__).parents[1]


class M125DomainPreflightTests(unittest.TestCase):
    def test_runtime_does_not_contain_gis_data_preflight_rules(self):
        source = (ROOT / "agent" / "runtime.py").read_text(encoding="utf-8")
        for token in (
            "_required_health_datasets",
            "_PIXEL_ALIGNMENT_TOOLS",
            "dem_land_use",
            "数据集 {dataset} 不可用",
        ):
            self.assertNotIn(token, source)
        self.assertIn("run_domain_preflight", source)

    def test_preflight_contract_delegates_required_datasets(self):
        calls = []

        class DomainPack:
            domain_id = "fixture"

            def preflight_tool(
                self,
                tool,
                arguments,
                completed_results,
                *,
                required_datasets=(),
                require_dependency_evidence=False,
            ):
                calls.append(
                    {
                        "tool": tool,
                        "arguments": arguments,
                        "completed_results": completed_results,
                        "required_datasets": tuple(required_datasets),
                        "require_dependency_evidence": require_dependency_evidence,
                    }
                )

        completed = {"health": {"capabilities": []}}
        preflight_tool(
            DomainPack(),
            "summarize_text",
            {"document": "demo"},
            completed,
            required_datasets=["documents"],
            require_dependency_evidence=True,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "summarize_text")
        self.assertEqual(calls[0]["required_datasets"], ("documents",))
        self.assertTrue(calls[0]["require_dependency_evidence"])
        self.assertIs(calls[0]["completed_results"], completed)

    def test_domain_without_preflight_hook_remains_valid(self):
        class DomainPack:
            domain_id = "fixture"

        preflight_tool(DomainPack(), "answer", {}, {})


if __name__ == "__main__":
    unittest.main()
