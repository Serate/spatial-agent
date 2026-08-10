"""Create a local dataset config bound to a generated manifest.

The output config is intended to remain outside version control.  It keeps
machine-specific roots and manifest locations out of the checked-in example.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


def bind_manifest(config_path: str, manifest_path: str, output_path: str) -> Path:
    config = Path(config_path)
    output = Path(output_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    manifest = Path(manifest_path).resolve()
    try:
        bound_path = os.path.relpath(manifest, output.parent.resolve()).replace("\\", "/")
    except ValueError:
        bound_path = str(manifest)
    payload["manifest"] = bound_path
    payload["manifest_required"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind a local dataset catalog to a manifest.")
    parser.add_argument("--config", required=True, help="checked-in dataset config template")
    parser.add_argument("--manifest", required=True, help="generated manifest path")
    parser.add_argument("--output", required=True, help="ignored local config output path")
    args = parser.parse_args()
    output = bind_manifest(args.config, args.manifest, args.output)
    print(json.dumps({"status": "ok", "config": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
