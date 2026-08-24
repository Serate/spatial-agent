"""Canonical source reader for static Console contracts.

The page shell and its application implementation are separate modules after
M258.  Tests that assert the browser-facing application contract should read
both through this helper instead of coupling to either physical file.
"""

from __future__ import annotations

from pathlib import Path


def read_console_source(root: Path) -> str:
    root = Path(root)
    source_root = root / "web" / "src"
    return "\n".join(
        (
            (source_root / "index.html").read_text(encoding="utf-8"),
            (source_root / "styles.css").read_text(encoding="utf-8"),
            (source_root / "console_app.js").read_text(encoding="utf-8"),
        )
    )
