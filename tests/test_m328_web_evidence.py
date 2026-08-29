"""Compact M328-B checks for the shared document-evidence projection."""

from __future__ import annotations

import unittest

from agent.result_summary import build_result_summary, normalize_result_summary


def _summary_for(web_result):
    return build_result_summary(
        {
            "status": "COMPLETED",
            "steps": [
                {
                    "id": "search",
                    "tool": "web_search",
                    "status": "COMPLETED",
                    "result": web_result,
                }
            ],
        }
    )


class M328WebEvidenceSummaryTests(unittest.TestCase):
    def test_success_sources_remain_structured_and_available(self):
        summary = _summary_for(
            {
                "schema_version": "spatial-agent.document-evidence.v1",
                "result_type": "document_evidence",
                "status": "ok",
                "query": "洪山区 2025 年经济指标",
                "allowed_domains": ["gov.cn"],
                "reason_code": "search_completed",
                "source_count": 1,
                "sources": [
                    {
                        "title": "官方统计公报",
                        "url": "https://www.gov.cn/report?id=1#fragment",
                        "domain": "www.gov.cn",
                        "snippet": "公开统计资料摘要",
                    }
                ],
            }
        )

        evidence = summary["blocks"][0]["evidence"]
        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["state"], "available")
        self.assertEqual(evidence["status"], "ok")
        self.assertEqual(evidence["source_records"][0]["title"], "官方统计公报")
        self.assertEqual(evidence["source_records"][0]["url"], "https://www.gov.cn/report?id=1")
        self.assertEqual(summary["evidence"]["source_records"][0]["domain"], "www.gov.cn")
        self.assertEqual(normalize_result_summary(summary), summary)

    def test_no_results_and_unavailable_are_distinguishable(self):
        no_results = _summary_for(
            {
                "schema_version": "spatial-agent.document-evidence.v1",
                "result_type": "document_evidence",
                "status": "ok",
                "reason_code": "search_no_results",
                "source_count": 0,
                "sources": [],
            }
        )
        unavailable = _summary_for(
            {
                "schema_version": "spatial-agent.document-evidence.v1",
                "result_type": "document_evidence",
                "status": "unavailable",
                "reason_code": "search_network_error",
                "source_count": 0,
                "sources": [],
            }
        )

        no_result_evidence = no_results["blocks"][0]["evidence"]
        unavailable_evidence = unavailable["blocks"][0]["evidence"]
        self.assertEqual(no_result_evidence["state"], "no_results")
        self.assertEqual(no_result_evidence["status"], "ok")
        self.assertEqual(unavailable_evidence["state"], "unavailable")
        self.assertEqual(unavailable_evidence["status"], "unavailable")
        self.assertTrue(any("没有找到相关资料" in item for item in no_results["limitations"]))
        self.assertTrue(any("当前不可用" in item for item in unavailable["limitations"]))


if __name__ == "__main__":
    unittest.main()
