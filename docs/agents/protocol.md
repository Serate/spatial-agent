# 多 Agent 并行开发协作协议

版本：`spatial-agent.agent-collaboration.v1`

本文档只约束项目开发协作，不改变产品 Runtime 的 `RunEvent`、Result、Evidence 或 HTTP
契约。主控 Agent 是唯一集成者；后端和前端 Agent 使用独立 worktree，并通过平台子代理
回传完成、阻塞或决策请求。

## 角色与权威来源

- `coordinator`：负责 Goal、Spec、Plan、公共契约、集成、阶段验收、交接文档和推送。
- `backend`：负责 Runtime、Planner、ToolRegistry、RunEvent、SSE、持久化、恢复和模型流。
- `frontend`：负责事件消费、阶段状态、答案流、分析摘要、地图和动态结果展示。

记忆优先级固定为：

```text
当前 Goal > 角色规约/本协议 > docs/agent-work-state.md > 当前任务卡
> tasks/task-progress.md 最近区块 > Git 状态 > 聊天上下文
```

发生冲突时，以版本化文件和当前分支状态为准，并在回传中报告冲突；不能用聊天记忆
静默覆盖项目状态。

## 任务分派消息

主控向子代理发送的任务必须包含以下内容：

```json
{
  "protocol_version": "spatial-agent.agent-collaboration.v1",
  "message_id": "stable-id",
  "task_id": "stage-role-task",
  "parent_task_id": "stage-task-or-null",
  "role": "backend|frontend",
  "base_revision": "commit-or-known-baseline",
  "objective": "one complete capability slice",
  "allowed_paths": ["path/to/file"],
  "forbidden_paths": ["path/to/file"],
  "dependencies": ["contract-or-task-id"],
  "contract_versions": ["contract-id@version"],
  "acceptance": ["observable condition"],
  "memory_inputs": ["role charter", "task card"]
}
```

任务必须有唯一负责人和不重叠的直接修改范围。公共契约、Goal、主交接快照和阶段计划
只能由主控修改。

## 子代理回传消息

子代理每次里程碑或结束时使用以下字段：

```json
{
  "protocol_version": "spatial-agent.agent-collaboration.v1",
  "message_id": "stable-id",
  "task_id": "stage-role-task",
  "role": "backend|frontend",
  "status": "STARTED|IN_PROGRESS|READY_FOR_REVIEW|DONE|BLOCKED|NEEDS_DECISION",
  "summary": "short safe summary",
  "changed_files": ["path/to/file"],
  "verification": ["command or result"],
  "blockers": [],
  "decision_request": null,
  "commit": "commit-or-null",
  "handoff": "next action for coordinator"
}
```

`DONE` 只表示子任务已完成并可审查，不表示阶段已经完成。主控必须审查 diff、契约、
文件边界和验证结果后再合并。

## 状态与通信

合法状态流转为：

```text
STARTED -> IN_PROGRESS -> READY_FOR_REVIEW -> DONE
                         ├-> BLOCKED
                         └-> NEEDS_DECISION
```

- 子代理完成、阻塞或需要决策时，优先通过平台回调直接通知主控。
- 主控不使用定时轮询；只有在下一关键步骤确实依赖结果时，才等待该任务的完成事件。
- `tasks/parallel/active/<role>.md` 保存可恢复状态，但不是实时消息总线。
- 子代理之间不直接互发修改指令，跨角色依赖由主控转发。
- 相同角色的后续任务继续使用原 `agent_id`；不存在时才创建替代会话。

## 安全边界

任何任务卡、回传、日志和提交都不得包含 API key、Prompt、模型原文、隐藏思维链、
完整错误堆栈、私有宿主路径或完整真实原始数据。真实模型调用、Docker 验收和生产分支
推送由主控统一执行。

## 阶段交付

每个阶段完成后由主控统一更新：

- `docs/agent-work-state.md` 顶部快照；
- `tasks/task-progress.md` 当前/最近完成区块；
- `tasks/task-state.md`（仅必要兼容状态）；
- `docs/agent-development-issues.md`（仅新增真实问题）；
- `docs/milestones.md`、阶段 Spec/Plan 和 `tasks/todo.md`。

阶段必须经过：全局规划 → Spec → Plan → 并行实现 → 集成验收 → 交接 → 全局重规划 →
提交推送。
