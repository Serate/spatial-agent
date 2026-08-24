"""M257: evidence recovery shares the canonical projection seam."""

import unittest
from pathlib import Path

from agent.evidence_projection import (
    EVIDENCE_RECOVERY_SCHEMA_VERSION,
    project_evidence_recovery,
)
from agent.evidence_recovery import (
    EVIDENCE_RECOVERY_SCHEMA_VERSION as COMPAT_SCHEMA_VERSION,
    project_evidence_recovery as compat_project_evidence_recovery,
)


class M257ContractEvidenceTests(unittest.TestCase):
    def test_compatibility_import_is_the_canonical_recovery_function(self):
        self.assertIs(compat_project_evidence_recovery, project_evidence_recovery)
        self.assertEqual(COMPAT_SCHEMA_VERSION, EVIDENCE_RECOVERY_SCHEMA_VERSION)

    def test_active_paths_import_the_combined_projection_seam(self):
        root = Path(__file__).parents[1]
        for relative in (
            "result_contract.py",
            "agent/artifact_viewer.py",
            "agent/service.py",
            "agent/service_async.py",
            "agent/application/http.py",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("from agent.evidence_recovery import", source, relative)
            self.assertNotIn("from .evidence_recovery import", source, relative)


if __name__ == "__main__":
    unittest.main()
