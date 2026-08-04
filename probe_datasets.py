import argparse
import json
from pathlib import Path

from agent.dataset_catalog import DatasetCatalog
from agent.dataset_probe import probe_catalog


def parse_args():
    parser = argparse.ArgumentParser(description="Probe vector and raster dataset metadata.")
    parser.add_argument(
        "--config",
        default="config/datasets.local.example.json",
        help="Dataset catalog config path.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=10,
        help="Maximum files to inspect per dataset.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write metadata JSON.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    catalog = DatasetCatalog.from_json(args.config)
    report = probe_catalog(catalog, max_files_per_dataset=args.max_files)
    payload = json.dumps(report, ensure_ascii=True, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
