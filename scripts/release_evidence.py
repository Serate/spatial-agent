"""Generate an explicit, full-hash release evidence report."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from domains.gis.adapters.release_evidence import release_evidence_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Spatial Agent release evidence report.")
    parser.add_argument("--config", help="dataset catalog JSON; defaults to SPATIAL_AGENT_DATASET_CONFIG")
    parser.add_argument("--output", required=True, help="UTF-8 JSON output path")
    parser.add_argument("--max-files", type=int, default=10)
    args = parser.parse_args()
    result = release_evidence_snapshot(args.config, max_files=args.max_files)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": output.name}, ensure_ascii=True))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
