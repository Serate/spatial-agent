"""Build or verify a reproducible dataset manifest.

Examples:
  python scripts/dataset_manifest.py --config config/datasets.wuhan.local.example.json --output outputs/wuhan.manifest.json
  python scripts/dataset_manifest.py --config config/datasets.wuhan.local.example.json --verify outputs/wuhan.manifest.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.dataset_catalog import DatasetCatalog
from agent.dataset_manifest import build_dataset_manifest, load_manifest, verify_dataset_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify a Spatial Agent dataset manifest.")
    parser.add_argument("--config", required=True, help="dataset catalog JSON")
    parser.add_argument("--output", help="manifest output path")
    parser.add_argument("--verify", metavar="MANIFEST", help="verify an existing manifest with SHA-256")
    parser.add_argument("--max-files", type=int, help="limit files per dataset when building")
    args = parser.parse_args()
    catalog = DatasetCatalog.from_json(args.config)
    if args.verify:
        result = verify_dataset_manifest(catalog, load_manifest(args.verify), verify_hashes=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ready" else 1
    if not args.output:
        parser.error("--output is required when --verify is not used")
    manifest = build_dataset_manifest(catalog, max_files_per_dataset=args.max_files)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output), "datasets": len(manifest["datasets"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
