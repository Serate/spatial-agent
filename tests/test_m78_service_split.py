"""M78.2 contract: the service facade delegates to focused modules and the
agent package never imports the root-level demo script."""

import unittest
from pathlib import Path


class M78ServiceSplitTests(unittest.TestCase):
    def test_agent_package_does_not_import_run_demo(self):
        package = Path(__file__).parents[1] / "agent"
        offenders = []
        for path in package.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "from run_demo import" in source or "import run_demo" in source:
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_facade_delegates_to_focused_modules(self):
        import agent.service as service
        import agent.service_async
        import agent.service_format
        import agent.service_sessions

        for module in (service, agent.service_async, agent.service_format, agent.service_sessions):
            self.assertIsNotNone(module.__file__)

        service_source = Path(service.__file__).read_text(encoding="utf-8")
        self.assertIn("from agent.application.service_async import", service_source)
        self.assertIn("from agent.application.service_format import", service_source)
        self.assertIn("from agent.application.service_sessions import", service_source)

    def test_runtime_factory_is_shared_and_run_demo_reexports_it(self):
        import run_demo
        from agent.runtime_factory import build_runtime as factory_build

        self.assertIs(run_demo.build_runtime, factory_build)

    def test_service_facade_keeps_public_methods(self):
        from agent.service import AgentService

        expected = {
            "run", "run_async", "retry", "cancel", "get_run",
            "list_runs", "list_session_runs", "list_sessions",
            "create_session", "clear_session", "delete_session",
            "metrics", "compare_buildability", "compare_buildability_regions",
        }
        missing = sorted(name for name in expected if not hasattr(AgentService, name))
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
