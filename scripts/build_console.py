#!/usr/bin/env python3
"""Build the dependency-free Console source tree into a static asset tree.

The Console intentionally has no npm build dependency.  This builder keeps
the deployment seam deterministic: every supported source asset is copied to
``web/dist`` and the HTTP adapters can serve that directory without knowing
how the page is implemented.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "web" / "src"
DIST_ROOT = ROOT / "web" / "dist"
SUPPORTED_SUFFIXES = frozenset({".html", ".css", ".js"})


def build() -> list[str]:
    if not SOURCE_ROOT.is_dir():
        raise SystemExit(f"Console source directory is missing: {SOURCE_ROOT}")

    files = sorted(
        path
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files or not (SOURCE_ROOT / "index.html").is_file():
        raise SystemExit("Console source tree must contain index.html and assets")

    if DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in files:
        relative = source.relative_to(SOURCE_ROOT)
        target = DIST_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.as_posix())
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate source inputs without writing dist")
    args = parser.parse_args()
    if args.check:
        required = (SOURCE_ROOT / "index.html", SOURCE_ROOT / "styles.css")
        missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
        if missing:
            print("missing console source: " + ", ".join(missing))
            return 1
        print(f"console source ready: {len(list(SOURCE_ROOT.rglob('*')))} entries")
        return 0
    copied = build()
    print(f"built web/dist: {len(copied)} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
