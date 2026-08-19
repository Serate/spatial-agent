"""Validate stable result equivalence for an acceptance boundary.

The production PowerShell acceptance script uses this small CLI so its
cross-entry comparison is backed by the same Python Contract Harness as the
offline CLI/HTTP/artifact/recovery tests.  Input is a JSON array of public
result payloads; file paths and transport identifiers are intentionally not
part of the comparison output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

# Running this file directly makes ``scripts`` the first import directory;
# explicitly add the repository root so the same package imports work from
# PowerShell, subprocess tests, and a checked-out production workspace.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.contract_harness import compare_results


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="JSON file containing a public result payload; one file may contain an array",
    )
    args = parser.parse_args(argv)

    try:
        loaded = [_load(Path(name)) for name in args.input]
        payloads = loaded[0] if len(loaded) == 1 and isinstance(loaded[0], list) else loaded
        differences = compare_results(payloads)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2

    report = {
        "status": "ok" if not differences else "mismatch",
        "entry_count": len(payloads),
        "differences": differences,
    }
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if not differences else 1


if __name__ == "__main__":
    raise SystemExit(main())
