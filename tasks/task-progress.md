# Agent 任务进度账本

> 当前账本只保留恢复所需的当前任务和最近交付。完整历史见
> `docs/archive/task-progress-history.md`，默认恢复不读取历史账本。

<!-- document-control: {"schema_version":"spatial-agent.document-control.v1","role":"active-ledger","archive_target":"docs/archive/task-progress-history.md","archive_block_prefix":"archive-block"} -->

## 使用规则

- 每个子任务开始、完成或暂停时，更新 `tasks/current-state.md`，再在本文件追加一条精简记录。
- 同步 `docs/agent-work-state.md` 时只更新当前状态，不复制历史过程。
- 记录目标、状态、修改文件、验证、阻塞和下一步；不记录 API key、Prompt、模型原文、完整私有数据或敏感异常。
- 阶段任务覆盖完整能力链；测试按独立风险合并，避免每个小改动重复全量回归。
- 上下文恢复默认只读热快照、当前状态和当前阶段 handoff；本文件只在明确需要进度历史时读取。

## 当前进行中

### M323：人工审批、持久化和 Registry 治理 — 规划中

- 目标：已验证的 M322 提案经过显式人工决策后，才能进入版本化 ToolRegistry；审批、拒绝、过期、撤销和重启恢复均可审计。
- 当前任务：M323-A，冻结 approval record、状态机、receipt fingerprint、版本和 HTTP 语义。
- 必要文件：`docs/document-index.json`、`docs/stages/M323/`、`scripts/resume_context.ps1`、`agent/tooling/proposal.py`、`agent/tools.py`、`agent/sqlite_store.py`、`agent/application/http.py`。
- 验证：文档索引和恢复脚本的 PowerShell/JSON/路径检查已通过；归档脚本 dry-run、真实归档和重复执行已通过；代码变更后只运行受影响契约、compileall、architecture strict 和 readiness。
- 阻塞：无。不得自动批准、执行未经批准源码、绕过 ToolRegistry 或保存敏感模型数据。
- 下一步：实现 M323 approval record 和状态机。

## 最近完成

<!-- archived-block-ref:document-index-restructure -->
### document-index-restructure — 已归档
- 详情：docs/archive/task-progress-history.md（归档块 document-index-restructure）

### M322：Python 工具提案与 Docker 沙箱 — 已完成

- 结果：完成 AST 校验、无网络 Docker sidecar、待审批 receipt；提案不会自动注册或在主进程执行。
- 验证：Docker M322 7/7；M318-M322 合并契约 43/43；compileall、architecture strict、smoke、readiness 200、sidecar socket 和 SQLite receipt 恢复通过。
- 交付：提交 `1b0bcdc` 已推送。
