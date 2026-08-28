# 当前任务状态

> 热状态文件，只保留当前阶段和最近一个交接点，建议控制在 60 行以内。历史过程见
> `task-progress.md`，默认恢复不读取历史账本。

## 当前阶段

- 阶段：M323 人工审批、持久化和 Registry 治理
- 当前任务：M323-A 文档与审批边界冻结
- 状态：规划中
- 最近交付：M322，提交 `1b0bcdc`

## 已完成

- M322 Python 工具提案、AST 校验、无网络 Docker sidecar 和待审批 receipt 已完成。
- 文档恢复架构重构方案已确定：热索引、阶段包、稳定知识、历史归档四层。

## 进行中

- 冻结 M323 approval record、状态转换、fingerprint、版本和 decision receipt 契约。
- 设计 SQLite 恢复及批准后 Registry 发布的边界；暂不修改 Runtime 主循环。

## 必要文件

- `docs/document-index.json`
- `docs/agent-work-state.md`
- `docs/task-resume.md`
- `docs/stages/M323/capability-map.md`
- `docs/stages/M323/spec.md`
- `docs/stages/M323/plan.md`
- `docs/stages/M323/handoff.md`
- `scripts/resume_context.ps1`
- `scripts/validate_document_index.ps1`
- `scripts/archive_document_sections.ps1`
- `tasks/plan.md`

## 验证

- `validate_document_index.ps1`：通过，active stage 为 M323，默认入口 4 个文件。
- `resume_context.ps1` 默认恢复和 `-Stage M323 -Topic 审批`：通过，输出保持有界。
- `archive_document_sections.ps1`：dry-run、真实归档和重复执行验证通过；已归档区块留下指针。
- Docker 不需要重跑；本轮只改文档索引与恢复脚本。

## 阻塞与下一步

- 阻塞：无。
- 下一步：开始 M323-A approval record 和状态机实现。
