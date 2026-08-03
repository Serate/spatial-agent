import argparse
import json

from agent.dataset_catalog import DatasetCatalog


def parse_args():
    parser = argparse.ArgumentParser(description="Inspect local spatial datasets.")
    parser.add_argument(
        "--config",
        default="config/datasets.local.example.json",
        help="Dataset catalog config path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    catalog = DatasetCatalog.from_json(args.config)
    print(json.dumps(catalog.summary(), ensure_ascii=False, indent=2))
