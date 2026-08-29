"""Generate a human-readable responsibility map for every ``agent/`` source file.

The source index is the machine-readable navigation contract.  This report is a
review surface for the current physical layout: it lists every module exactly
once, keeps responsibility text short, and deliberately does not recommend a
physical move.  It can therefore be regenerated after a file is added or a
responsibility override changes without copying source code into documentation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def build_report(index: dict[str, Any]) -> str:
    entries = [
        entry
        for entry in index.get("files", [])
        if isinstance(entry, dict) and str(entry.get("path", "")).startswith("agent/")
    ]
    entries.sort(key=lambda entry: str(entry.get("path", "")))
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        groups[_physical_group(str(entry["path"]))].append(entry)

    semantic = index.get("semantic_index", {})
    lines = [
        "# `agent/` 全量模块职责地图",
        "",
        "> 本文件由 `scripts/build_agent_module_map.py` 根据 `docs/code-index.json` 生成。",
        "> 它是当前职责盘点，不是物理迁移方案；下一阶段再根据整体依赖和 seam 评估目录调整。",
        "> 文档不复制源码正文，只保留职责、语义层、稳定性、阶段和验证入口。",
        "",
        "## 使用边界",
        "",
        "- `职责` 是恢复上下文和代码导航的第一入口；`层` 是当前语义分类，不等于立即迁移目标。",
        "- `来源` 为 `file-override` 时，职责由精确文件规则维护；为 `path-rule` 时，职责继承目录/文件族规则。",
        "- `导出符号数` 和 `验证入口` 用于快速定位深模块接口与最小验证面，详细符号仍在 `docs/code-index.json`。",
        "- 新增或重命名 `agent/` 源码后，必须重新生成本报告并通过索引校验。",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| `agent/` 源码文件 | {len(entries)} |",
        f"| 全仓源码文件 | {index.get('file_count', '—')} |",
        f"| 职责覆盖 | {semantic.get('agent_files_with_responsibility', '—')}/{len(entries)} |",
        f"| 语义覆盖率 | {semantic.get('coverage_percent', '—')}% |",
        "",
        "### 语义层分布",
        "",
        "| 层 | 文件数 |",
        "| --- | ---: |",
    ]
    layer_counts = Counter(str(entry.get("layer", "unclassified")) for entry in entries)
    lines.extend(
        f"| `{layer}` | {count} |"
        for layer, count in sorted(layer_counts.items())
    )
    lines.extend(
        [
            "",
            "### 当前物理目录分布",
            "",
            "| 当前目录 | 文件数 | 主要语义层 |",
            "| --- | ---: | --- |",
        ]
    )
    for group, group_entries in groups.items():
        group_layers = ", ".join(
            f"{layer} ({count})"
            for layer, count in sorted(
                Counter(str(entry.get("layer", "unclassified")) for entry in group_entries).items()
            )
        )
        lines.append(f"| `{group}` | {len(group_entries)} | {group_layers} |")

    lines.extend(["", "## 文件职责清单", ""])
    for group, group_entries in groups.items():
        lines.extend(
            [
                f"### `{group}`",
                "",
                "| 文件 | 层 | 职责 | 稳定性 | 阶段 | 来源 | 导出 | 验证入口 |",
                "| --- | --- | --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for entry in group_entries:
            path = _cell(entry.get("path"))
            layer = _cell(entry.get("layer"))
            responsibility = _cell(entry.get("responsibility") or entry.get("role") or "未分类")
            stability = _cell(entry.get("stability"))
            stage = _cell(entry.get("stage") or "—")
            source = _cell(entry.get("semantic_source"))
            symbol_count = len(entry.get("public_symbols", [])) if isinstance(entry.get("public_symbols"), list) else 0
            tests = entry.get("tests")
            if isinstance(tests, list) and tests:
                test_text = "<br>".join(f"`{_cell(test)}`" for test in tests)
            else:
                test_text = "—"
            lines.append(
                f"| `{path}` | `{layer}` | {responsibility} | `{stability}` | `{stage}` | `{source}` | {symbol_count} | {test_text} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 盘点结论",
            "",
            "- 当前 `agent/` 已形成 Runtime、Application、Planner、Tooling、Domain、Persistence、Evidence、Result、Verification 和 Frontend 等职责簇。",
            "- `agent/` 根目录仍同时承载公共契约、兼容 facade 和稳定入口；这不是单凭文件名就能安全迁移的同质目录。",
            "- 下一阶段应结合导入图、公共稳定性、测试入口和实际 seam 决定是否迁移；仅有一个实现且调用方广泛的模块优先保持深模块与稳定入口。",
            "- 本清单完成的是“文件职责可见化”，不宣称已经完成逐行架构审计或物理目录重构。",
            "",
        ]
    )
    return "\n".join(lines)


def _physical_group(path: str) -> str:
    parts = Path(path).parts
    if len(parts) <= 2:
        return "agent/（根目录公共入口与契约）"
    return f"agent/{parts[1]}/"


def _cell(value: Any) -> str:
    text = str(value if value is not None else "—")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--index", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    index_path = (args.index or repo_root / "docs/code-index.json").resolve()
    output_path = (args.output or repo_root / "docs/agent-module-responsibilities.md").resolve()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_report(index), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": output_path.relative_to(repo_root).as_posix()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
