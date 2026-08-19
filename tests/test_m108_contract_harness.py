import unittest

from evaluation.contract_harness import compare_results, normalize_result


def _payload(answer="完成"):
    return {
        "status": "COMPLETED",
        "answer": answer,
        "steps": [{"tool": "range_query", "status": "COMPLETED", "governance": {"timeout": 10}}],
        "trace_summary": ["one"],
        "context_evidence": {"section_names": ["capability_catalog"]},
        "result": {
            "type": "admin_area_result",
            "title": "行政区边界",
            "request_facts": {"admin_name": "洪山区"},
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


class M108ContractHarnessTests(unittest.TestCase):
    def test_normalized_contract_ignores_transport_specific_fields(self):
        first = _payload()
        second = _payload()
        first["run_id"] = "run-a"
        second["run_id"] = "run-b"
        self.assertEqual(compare_results([first, second]), [])

    def test_compare_results_reports_bounded_field_path(self):
        changed = _payload(answer="另一份答案")
        differences = compare_results([_payload(), changed])
        self.assertIn("entry[0] vs entry[1]: $.answer", differences)

    def test_normalized_contract_is_json_safe(self):
        payload = normalize_result(_payload()).as_dict()
        self.assertEqual(payload["result_type"], "admin_area_result")
        self.assertEqual(payload["view_kinds"], {"steps": "steps"})

    def test_normalize_rejects_missing_public_envelope(self):
        with self.assertRaisesRegex(ValueError, "result envelope"):
            normalize_result({"status": "COMPLETED"})


if __name__ == "__main__":
    unittest.main()
