# M323 阶段交接

## 当前状态

- 阶段：M323 人工审批、持久化和 Registry 治理
- 当前任务：M323-A，审批契约和状态机
- 状态：规划中
- 前置版本：M322 `1b0bcdc`
- 恢复入口：`docs/agent-work-state.md`、`tasks/current-state.md`、本文件

## 已完成

- M322 已提供脱敏 `tool-proposal-receipt.v1`，合法提案只能停留在 `awaiting_approval`。
- 文件功能索引生成器已扩展为 Python/JavaScript，Docker 已生成 299 个源码文件（260 Python、39 JavaScript）。
- 文档索引已分为热状态、阶段包、稳定知识和历史归档四层。
- 文档架构校验已通过，默认恢复只读取热快照、索引、当前状态和本交接文件。

## 进行中

- 源码索引生成、校验和恢复主题查询已收口；下一步开始 approval record 状态机。

## 必要文件

- `docs/stages/M323/capability-map.md`
- `docs/stages/M323/spec.md`
- `docs/stages/M323/plan.md`
- `docs/code-index.json`
- `docs/code-index-overrides.json`
- `agent/tooling/proposal.py`
- `agent/tooling/__init__.py`
- `agent/tools.py`
- `agent/sqlite_store.py`
- `agent/application/http.py`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m323_tool_approval.py`（待创建）

## 验证与阻塞

- `validate_document_index.ps1` 和 `resume_context.ps1` 默认/M323 主题恢复验证通过。
- `build_code_index.py` 已支持 Python/JavaScript；索引计数、符号行号、文档索引和主题查询均已校验通过。
- `validate_code_index.ps1` 已修复为仅校验覆盖项实际声明的测试路径，前端无测试覆盖时不会误报空路径。
- 本阶段不重复运行 Docker 业务测试；本轮仅使用 Docker 生成索引，并运行索引/文档恢复校验。
- 阻塞：无。

## 下一步

先完成 approval record 的 schema 和状态机，再接 SQLite、Registry gate、HTTP 语义和最小测试。
