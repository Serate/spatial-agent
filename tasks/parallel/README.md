# 并行任务目录

本目录保存并行开发的任务卡和角色状态。它不是产品运行数据，也不是实时消息总线。

## 目录约定

- `task-template.md`：任务卡模板；
- `active/backend.md`、`active/frontend.md`：当前子代理状态；
- `active/<task-id>.md`：需要多个独立任务时使用；
- `.agent-state/`：本地会话 ID 和临时状态，位于仓库外部记忆边界，不提交到 Git。

主控负责维护 `docs/agent-work-state.md`；子代理只维护自己的状态文件并通过平台回调
报告，不直接修改主控快照。

## 文件命名

任务卡使用 `<阶段>-<角色>-<任务>.md`，例如 `m313-backend-answer-stream.md`。
角色状态使用固定角色名，便于上下文恢复和同一 `agent_id` 续接。
