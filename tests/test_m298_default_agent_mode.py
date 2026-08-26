import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.application.http import HTTPApplication
from agent.composite_contract import inherit_composite_runtime_selection
from agent.runtime_defaults import (
    DEFAULT_BACKEND,
    DEFAULT_PLANNER,
    product_defaults,
)


class _Service:
    def run(self, **kwargs):
        return kwargs

    def capabilities(self, **kwargs):
        return kwargs


class _Composite:
    def __init__(self):
        self.payload = None

    def run(self, payload, *, session_id):
        self.payload = payload
        return {"status": "COMPLETED", "session_id": session_id}


class M298DefaultAgentModeTests(unittest.TestCase):
    def test_product_defaults_are_real_model_and_local(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPATIAL_AGENT_DEFAULT_PLANNER", None)
            os.environ.pop("SPATIAL_AGENT_DEFAULT_BACKEND", None)
            self.assertEqual(
                product_defaults(),
                {"planner": DEFAULT_PLANNER, "backend": DEFAULT_BACKEND},
            )

    def test_environment_override_is_allowlisted_and_invalid_values_fallback(self):
        with patch.dict(
            os.environ,
            {
                "SPATIAL_AGENT_DEFAULT_PLANNER": "rule",
                "SPATIAL_AGENT_DEFAULT_BACKEND": "memory",
            },
        ):
            self.assertEqual(
                product_defaults(), {"planner": "rule", "backend": "memory"}
            )
        with patch.dict(
            os.environ,
            {
                "SPATIAL_AGENT_DEFAULT_PLANNER": "arbitrary",
                "SPATIAL_AGENT_DEFAULT_BACKEND": "remote",
            },
        ):
            self.assertEqual(
                product_defaults(),
                {"planner": DEFAULT_PLANNER, "backend": DEFAULT_BACKEND},
            )

    def test_http_application_injects_defaults_but_preserves_explicit_offline_path(self):
        application = HTTPApplication(_Service(), use_product_defaults=True)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPATIAL_AGENT_DEFAULT_PLANNER", None)
            os.environ.pop("SPATIAL_AGENT_DEFAULT_BACKEND", None)
            defaulted = application.execute("run", {"request": "开放式分析"})
        explicit = application.execute(
            "run",
            {"request": "离线分析", "planner": "rule", "backend": "memory"},
        )
        self.assertEqual(
            (defaulted["planner"], defaulted["backend"]), ("openai", "local")
        )
        self.assertEqual(
            (explicit["planner"], explicit["backend"]), ("rule", "memory")
        )

    def test_low_level_http_application_keeps_offline_fallbacks(self):
        application = HTTPApplication(_Service())
        result = application.execute("run", {"request": "离线分析"})
        self.assertEqual((result["planner"], result["backend"]), ("rule", "memory"))

    def test_composite_components_inherit_one_top_level_selection(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "跨领域分析",
            "components": [
                {
                    "component_id": "gis-part",
                    "domain_id": "gis",
                    "request": "查询空间结果",
                },
                {
                    "component_id": "economic-part",
                    "domain_id": "economic",
                    "request": "查询指标趋势",
                    "planner": "rule",
                    "backend": "memory",
                },
            ],
        }
        selected = inherit_composite_runtime_selection(
            request, planner="openai", backend="local"
        )
        self.assertEqual(
            [(item["planner"], item["backend"]) for item in selected["components"]],
            [("openai", "local"), ("openai", "local")],
        )
        self.assertNotEqual(request["components"][0].get("planner"), "openai")

    def test_http_composite_boundary_applies_selection_before_dispatch(self):
        composite = _Composite()
        application = HTTPApplication(
            _Service(), composite=composite, use_product_defaults=True
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPATIAL_AGENT_DEFAULT_PLANNER", None)
            os.environ.pop("SPATIAL_AGENT_DEFAULT_BACKEND", None)
            application.execute(
                "composite_run",
                {
                    "request": "组合分析",
                    "session_id": "m298",
                    "components": [
                        {
                            "component_id": "one",
                            "domain_id": "gis",
                            "request": "空间摘要",
                        }
                    ],
                },
            )
        component = composite.payload["components"][0]
        self.assertEqual((component["planner"], component["backend"]), ("openai", "local"))

    def test_frontend_has_default_visible_agent_stage_surface(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "src" / "index.html").read_text(encoding="utf-8")
        script = (root / "web" / "src" / "console_app.js").read_text(encoding="utf-8")
        self.assertIn('id="agentStageBar"', html)
        for label in ("发现能力", "理解请求", "生成计划", "执行任务", "汇总结果"):
            self.assertIn(label, script)
        self.assertIn("renderAgentStageBar('IDLE')", script)


if __name__ == "__main__":
    unittest.main()
