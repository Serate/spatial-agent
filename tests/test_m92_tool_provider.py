import unittest
from pathlib import Path

from agent.capability_catalog import capability_catalog, capability_context_summary
from agent.errors import ToolError
from agent.planner import RuleBasedPlanner
from agent.runtime import AgentRuntime
from agent.tool_provider import NativeToolProvider
from agent.tools import DemoSpatialAdapter, ToolRegistry


ROOT = Path(__file__).parents[1]


class EchoAdapter:
    def __init__(self):
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return {'echo': arguments['value']}


def echo_definitions():
    return {
        'echo': {
            'name': 'echo',
            'input_schema': {
                'type': 'object',
                'required': ['value'],
                'properties': {'value': {'type': 'string'}},
                'additionalProperties': False,
            },
        }
    }


class ExternalLikeProvider:
    provider_id = 'external-like'

    def definitions(self):
        return echo_definitions()

    def invoke(self, name, arguments):
        return {'echo': 'external:' + arguments['value']}


class M92ToolProviderTests(unittest.TestCase):
    def test_native_provider_can_feed_registry_without_exposing_adapter(self):
        adapter = EchoAdapter()
        registry = ToolRegistry.from_provider(NativeToolProvider(echo_definitions(), adapter))

        self.assertEqual(registry.provider_info(), {'id': 'native', 'tool_count': 1})
        self.assertEqual(registry.invoke('echo', {'value': 'ok'}), {'echo': 'ok'})
        self.assertEqual(adapter.calls, [('echo', {'value': 'ok'})])

    def test_registry_validates_before_provider_invocation(self):
        adapter = EchoAdapter()
        registry = ToolRegistry.from_provider(NativeToolProvider(echo_definitions(), adapter))

        with self.assertRaises(ToolError) as context:
            registry.invoke('echo', {})
        self.assertIn('missing required fields', str(context.exception))
        self.assertEqual(adapter.calls, [])

    def test_registry_accepts_a_non_native_provider_at_the_same_seam(self):
        registry = ToolRegistry.from_provider(ExternalLikeProvider())

        self.assertEqual(registry.provider_info()['id'], 'external-like')
        self.assertEqual(registry.invoke('echo', {'value': 'ok'}), {'echo': 'external:ok'})

    def test_capability_context_records_safe_provider_identity(self):
        summary = capability_context_summary(
            catalog=capability_catalog(environment='memory'),
            tool_definitions={
                'get_raster_metadata': {
                    'input_schema': {'type': 'object'},
                    'output_schema': {'type': 'object'},
                }
            },
            tool_provider={'id': 'native', 'tool_count': 16},
            selected_capability_ids=['raster_metadata'],
            max_capabilities=1,
            max_tools=1,
        )

        self.assertEqual(summary['tool_provider'], {'id': 'native', 'tool_count': 16})
        self.assertEqual(summary['tool_schema_count'], 1)

    def test_runtime_plan_evidence_includes_provider_identity(self):
        registry = ToolRegistry.from_json(
            str(ROOT / 'tools' / 'schema' / 'tool-definitions.json'),
            DemoSpatialAdapter(),
        )
        result = AgentRuntime(RuleBasedPlanner(), registry).run('查询DEM栅格元数据')

        self.assertEqual(result.status.value, 'COMPLETED')
        self.assertEqual(
            result.plan_evidence['capability_catalog_tool_provider']['id'],
            'native',
        )


if __name__ == '__main__':
    unittest.main()
