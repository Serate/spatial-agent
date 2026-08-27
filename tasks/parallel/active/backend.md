# 后端协作试运行任务卡

任务编号：`collab-prep-backend-20260827`
角色：`backend`
状态：已完成
父任务：`collab-prep-20260827`
基线提交：`1b7dd7b`（实际工作树可能包含未提交的 M313 变更，试运行不得修改它们）

## 目标

验证后端角色能依据角色规约、协作协议和有界上下文包理解任务，并按统一格式回传，不修改仓库。

## 允许修改

- 无。仅阅读和回传。

## 禁止修改

- 全部项目文件；尤其是 `agent/`、`docs/agent-work-state.md` 和 `tasks/task-progress.md`。

## 依赖与契约

- `docs/agents/roles/backend.md`
- `docs/agents/protocol.md`
- `spatial-agent.agent-collaboration.v1`

## 验收标准

- 识别后端职责和禁止边界；
- 返回 `STARTED` 或 `READY_FOR_REVIEW` 语义；
- 明确说明没有修改文件、没有运行命令、没有读取敏感信息；
- 回传包含任务编号、状态、摘要、阻塞和下一步。

## 最终回传

- 状态：READY_FOR_REVIEW
- 实际改动文件：无
- 验证结果：只读理解任务卡、后端角色规约和协作协议；未运行 Python、Docker、浏览器或真实模型。
- 阻塞/决策请求：无
- 提交：无
- 交接给主控：后端角色可按固定任务编号回传，并已验证同一 agent_id 关闭后恢复续接。
