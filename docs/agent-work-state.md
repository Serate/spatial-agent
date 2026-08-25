# Agent 当前工作快照

> 本文件是新对话或上下文压缩后的唯一工作入口。恢复脚本默认只读取本文件；不要自动读取完整恢复卡、历史问题日志、milestones、归档、完整测试或模型响应。
>
> 每完成一个子任务，必须先更新本文件的“任务记录”和“下一步”；阶段完成后再同步 `docs/agent-context-resume.md`、`docs/milestones.md` 和 `tasks/`，提交并推送。

## Goal 摘要

建设可测试、可观测、可替换、可恢复的领域中立 Agent Runtime；GIS 只是业务载体。系统通过能力目录、Planner、TaskPlan/DAG、ToolRegistry、统一生命周期、Result/View/Artifact/Evidence 支撑开放式、多领域、可恢复分析，不为单一区域、单一问句或单一数据集增加硬编码流程。

### Goal 追加约束：压缩上下文恢复

- 恢复时只读取本文件、当前阶段对应的 Spec/Plan、最近进行中的任务记录和任务明确列出的待修改文件。
- 不默认读取完整历史恢复卡、问题日志、milestones、归档、全量测试、模型响应或无关源码；只有当前任务明确需要时才按文件读取。
- 每个进行中/已完成子任务必须记录：状态、改动文件、验证命令/结果、阻塞原因和下一步。
- 当前快照必须保持短小；历史细节留在阶段文档或问题日志，由快照只保留指针和结论。

## 当前阶段

- 阶段：M278 Composite 可恢复生命周期。
- 状态：进行中；恢复机制已收口，继续 M278 实现。
- 阶段规划：
  - [`docs/m278-composite-lifecycle-capability-map.md`](m278-composite-lifecycle-capability-map.md)
  - [`docs/m278-composite-lifecycle-spec.md`](m278-composite-lifecycle-spec.md)
  - [`docs/m278-composite-lifecycle-plan.md`](m278-composite-lifecycle-plan.md)
  - [`tasks/plan.md`](../tasks/plan.md)
  - [`tasks/todo.md`](../tasks/todo.md)

## 最近进行中的任务

### M278-A Composite Envelope（进行中）

- 目标：让 canonical Composite Result 能进入 `AgentRunResult`、SQLite 和 artifact 恢复边界。
- 已做：新增 `tests/test_m278_composite_lifecycle.py` 的 SQLite round-trip 用例；当前 Docker 镜像尚未重建，容器暂时看不到新测试文件。
- 待读/待修改文件：
  - `agent/models.py`
  - `agent/sqlite_store.py`
  - `agent/application/async_runs.py`
  - `agent/application/run_recovery.py`
  - `tests/test_m278_composite_lifecycle.py`
- 下一步：先为 `AgentRunResult` 增加可选 `result` 字段并完成 SQLite rehydrate；再在 Docker 重建后运行该用例。
- 当前阻塞：无代码阻塞；仅需重建 Docker 镜像以加载新测试和源码。

## 已完成记录

- 上下文恢复机制已完成：新增本快照、更新 `resume_context.ps1` 默认读取路径和历史开关，并同步恢复文档与中文问题日志；本地脚本输出验证通过，默认不加载历史文件。
- M277 已完成并推送：`e0104b8 feat: expose composite runs over http`。
- M277 Docker 定向 16/16、compileall、architecture strict、CI/stage、生产 `/health/ready` 通过。
- M278 能力图、Spec、Plan 已创建；尚未提交，属于当前工作树变更。
- 已安装 GitHub `sivaprasadreddy/sdd-skills` 的 `sdd-feature` 技能到 Codex 技能目录；该安装不修改项目仓库。

## 当前工作树变更

- `tasks/plan.md`
- `tasks/todo.md`
- `docs/m278-composite-lifecycle-capability-map.md`
- `docs/m278-composite-lifecycle-spec.md`
- `docs/m278-composite-lifecycle-plan.md`
- `tests/test_m278_composite_lifecycle.py`
- `docs/agent-work-state.md`
- `scripts/resume_context.ps1`
- `docs/task-resume.md`
- `docs/agent-context-resume.md`
- `docs/agent-development-issues.md`
- 本快照机制变更待单独提交；M278 规划和测试仍未完成。

## 最近任务记录

### 上下文恢复最小快照（已完成，待提交）

- 改动：用 `agent-work-state.md` 替代长恢复卡作为默认入口；默认只读当前快照，历史检索需显式 `-IncludeHistory`。
- 验证：`pwsh -NoProfile -File scripts/resume_context.ps1` 成功；`git diff --check` 通过。
- 结果：恢复输出包含当前 goal 摘要、M278 规划指针、最近任务、待修改文件、验证约定和下一步；未读取完整历史文件。
- 下一步：提交本次恢复机制改动后，继续 M278-A Envelope。

## 本阶段验证约定

- Python、GIS、compileall 和架构检查只在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持精简、离线；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 读取本文件。
2. 只读取上面列出的 M278 Spec/Plan 和当前任务待修改文件。
3. 继续 M278-A 的红→绿测试循环。
4. 完成一个子任务后立即更新本文件，再更新 `tasks/todo.md`。
