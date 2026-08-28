# M323 阶段交接

## 当前状态

- 阶段：M323 人工审批、持久化和 Registry 治理
- 当前任务：M323-A，审批契约和状态机
- 状态：规划中
- 前置版本：M322 `1b0bcdc`
- 恢复入口：`docs/agent-work-state.md`、`tasks/current-state.md`、本文件

## 已完成

- M322 已提供脱敏 `tool-proposal-receipt.v1`，合法提案只能停留在 `awaiting_approval`。
- 文档索引已分为热状态、阶段包、稳定知识和历史归档四层。
- 文档架构校验已通过，默认恢复只读取热快照、索引、当前状态和本交接文件。

## 进行中

- 冻结 approval record、状态转换、fingerprint、版本和 decision receipt 契约。
- 设计 SQLite 恢复及批准后 Registry 发布的边界；暂不修改 Runtime 主循环。

## 必要文件

- `docs/stages/M323/capability-map.md`
- `docs/stages/M323/spec.md`
- `docs/stages/M323/plan.md`
- `agent/tooling/proposal.py`
- `agent/tooling/__init__.py`
- `agent/tools.py`
- `agent/sqlite_store.py`
- `agent/application/http.py`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m323_tool_approval.py`（待创建）

## 验证与阻塞

- `validate_document_index.ps1` 和 `resume_context.ps1` 默认/M323 主题恢复验证通过。
- 本阶段不重复运行 Docker 业务测试；代码变更后再运行受影响契约。
- 阻塞：无。

## 下一步

先完成 approval record 的 schema 和状态机，再接 SQLite、Registry gate、HTTP 语义和最小测试。
