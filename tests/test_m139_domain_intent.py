"""M139 checks that intent policy belongs to the selected Domain Pack."""

from pathlib import Path
import unittest

from agent.spatial_intent import classify_spatial_intent
from agent.domain_contract import clarification_details as resolve_clarification_details
from domains.gis.intent import clarification_details
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.gis.planner import RuleBasedPlanner
from agent.errors import ClarificationNeeded
from run_demo import build_runtime


ROOT = Path(__file__).resolve().parents[1]


class _BareClarifyingPlanner:
    def plan(self, request, **kwargs):
        raise ClarificationNeeded("需要更多空间条件")


class M139DomainIntentTests(unittest.TestCase):
    def test_gis_policy_is_domain_owned_and_legacy_facade_is_thin(self):
        facade = (ROOT / "agent" / "spatial_intent.py").read_text(encoding="utf-8")
        implementation = (ROOT / "domains" / "gis" / "intent.py").read_text(encoding="utf-8")

        self.assertNotIn("行政区", facade)
        self.assertNotIn("道路", facade)
        self.assertIn("行政区", implementation)
        self.assertIn("importlib.import_module", facade)

        result = classify_spatial_intent("分析洪山区 DEM 空间分布")
        self.assertTrue(result["is_spatial"])
        self.assertIn("zonal_raster_statistics", result["matched_capabilities"])
        self.assertEqual(
            clarification_details("查询道路与水体分布")["schema_version"],
            "spatial-agent.clarification.v1",
        )
        self.assertEqual(
            resolve_clarification_details(GIS_DOMAIN_PACK, "查询道路与水体分布")[
                "schema_version"
            ],
            "spatial-agent.clarification.v1",
        )

    def test_gis_planner_imports_domain_policy_directly(self):
        source = (ROOT / "domains" / "gis" / "rule_planning.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("from agent.spatial_intent", source)
        self.assertIn("from .intent import", source)
        with self.assertRaises(ClarificationNeeded):
            RuleBasedPlanner().plan("查询武汉城市绿地空间分布")

    def test_runtime_enriches_bare_planner_clarification_from_domain(self):
        from agent.runtime import AgentRuntime
        from agent.tools import ToolRegistry
        from domains.gis.domain import GIS_DOMAIN_PACK

        registry = ToolRegistry.from_provider(
            GIS_DOMAIN_PACK.tool_provider(backend_name="memory", root=ROOT)
        )
        runtime = AgentRuntime(_BareClarifyingPlanner(), registry, domain_pack=GIS_DOMAIN_PACK)

        payload = runtime.preview("查询道路与水体分布")

        self.assertEqual(payload["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(
            payload["clarification"]["schema_version"],
            "spatial-agent.clarification.v1",
        )


if __name__ == "__main__":
    unittest.main()
