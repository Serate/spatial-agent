"""Verify source files recorded by an analysis-ready derivation report."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.analysis_ready_binding import verify_source_binding
from agent.dataset_catalog import DatasetCatalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify analysis-ready source binding.")
    parser.add_argument("--source-config", required=True, help="source dataset catalog JSON")
    parser.add_argument("--report", required=True, help="analysis-ready report JSON")
    args = parser.parse_args()
    catalog = DatasetCatalog.from_json(args.source_config)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    result = verify_source_binding(catalog, report.get("source_binding"))
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
