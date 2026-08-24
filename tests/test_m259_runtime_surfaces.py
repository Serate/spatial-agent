"""M259: Runtime state and capability surfaces stay canonical and reusable."""

from __future__ import annotations

import unittest

from agent.runtime import InMemoryConversationStore, InMemoryStateStore
from agent.runtime_core.capabilities import RuntimeCapabilitySurface
from agent.runtime_state import (
    InMemoryConversationStore as CanonicalConversationStore,
    InMemoryStateStore as CanonicalStateStore,
)
from domains.text.runtime import build_text_runtime


class M259RuntimeSurfaceTests(unittest.TestCase):
    def test_legacy_runtime_state_names_are_one_way_facades(self):
        self.assertIs(InMemoryStateStore, CanonicalStateStore)
        self.assertIs(InMemoryConversationStore, CanonicalConversationStore)

    def test_runtime_owns_one_capability_surface(self):
        runtime = build_text_runtime()
        self.assertIsInstance(runtime._capability_surface, RuntimeCapabilitySurface)
        self.assertEqual(runtime.capability_catalog()["domain_id"], "text")
        contract = runtime.workflow_contract()
        self.assertEqual(contract["domain_id"], "text")
        self.assertIn("known_tools", contract)

    def test_capability_snapshot_keeps_deployment_evidence(self):
        runtime = build_text_runtime()
        snapshot = runtime.runtime_capabilities(max_files=1)
        self.assertEqual(snapshot["domain_id"], "text")
        self.assertIn("deployment_evidence", snapshot)
        self.assertIn("runtime_context", snapshot)


if __name__ == "__main__":
    unittest.main()
