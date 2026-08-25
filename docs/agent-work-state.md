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
- 状态：进行中；M278-C HTTP 与 M278-D 重启接管已完成，进入阶段级 Docker 门禁。
- 阶段规划：
  - [`docs/m278-composite-lifecycle-capability-map.md`](m278-composite-lifecycle-capability-map.md)
  - [`docs/m278-composite-lifecycle-spec.md`](m278-composite-lifecycle-spec.md)
  - [`docs/m278-composite-lifecycle-plan.md`](m278-composite-lifecycle-plan.md)
  - [`tasks/plan.md`](../tasks/plan.md)
  - [`tasks/todo.md`](../tasks/todo.md)

## 最近进行中的任务

### M278-A Composite Envelope（已完成）

- 目标：让 canonical Composite Result 能进入 `AgentRunResult`、SQLite 和 artifact 恢复边界。
- 已做：为 `AgentRunResult` 增加可选 canonical `result` 字段，并在 SQLite `_result_from_dict()` 中恢复；新增 SQLite round-trip 用例。
- 待读/待修改文件：
  - `agent/models.py`
  - `agent/sqlite_store.py`
  - `agent/application/async_runs.py`
  - `agent/application/run_recovery.py`
  - `tests/test_m278_composite_lifecycle.py`
- 验证：重建 Docker 镜像后，`M278CompositeEnvelopeTests.test_composite_result_survives_sqlite_roundtrip` **1/1** 通过。
- 结果：Composite Result 的 type、schema 和 request fingerprint 可跨 SQLite 保存/恢复。
- 当前阻塞：无。

### M278-B CompositeRunApplication（已完成）

- 目标：通过现有 `AsyncApplication` 提供 Composite 同步持久化、异步幂等、artifact 和重启 recovery。
- 待读/待修改文件：
  - `agent/application/composite_runs.py`（新增）
  - `agent/application/composite.py`
  - `agent/service_state.py`
  - `agent/domain_runtime_host.py`
  - `production_api.py`
  - `serve_api.py`
  - `tests/test_m278_composite_lifecycle.py`
- 已做：新增 `agent/application/composite_runs.py`，注入现有 `AsyncApplication`、`ServiceState`、SQLite 和 `ArtifactStore`；Composite 使用隔离的 `composite` 持久化 scope。
- 验证：Docker `tests.test_m278_composite_lifecycle` **3/3** 通过，覆盖同步查询、异步幂等和无 SQLite snapshot 的 artifact 恢复。
- 结果：M278-B 不复制 worker 状态机；Composite 结果通过 canonical `result` 字段进入 shared async observability。
- 当前阻塞：无。

### M278-C Shared HTTP recovery commands（已完成）

- 目标：通过 `HTTPApplication` 暴露 Composite async submit、detail、observability 和 evidence；FastAPI/stdlib 只做 URL 胶水。
- 待读/待修改文件：
  - `agent/application/http.py`
  - `production_api.py`
  - `serve_api.py`
  - `tests/test_m278_composite_http.py`
- 已做：`HTTPApplication` 提供 Composite async submit、detail、observability、evidence 四个语义命令；FastAPI 与 stdlib 两个入口均只做 URL/状态码映射。
- 验证：Docker M278 定向测试中 HTTP Application、FastAPI 路由和 stdlib async/detail/observability/evidence 路由通过；当前联合结果 **7/7**。
- 结果：两个传输入口共享同一语义分发，async 提交和三类读取路径无双份生命周期逻辑。
- 当前阻塞：无。

### M278-D SQLite restart recovery（已完成）

- 目标：验证 Composite async job 在 owner 进程失效后由新实例接管，且只执行一次并保留 canonical result。
- 已做：新增孤儿 `RUNNING` job 验收；新 `CompositeRunApplication` 自动 claim，完成后 `recovery_count=1`，重复 `recover()` 不再执行。
- 改动文件：
  - `tests/test_m278_composite_lifecycle.py`
- 验证：Docker `test_restart_claims_orphan_once_and_preserves_composite_result` 通过。
- 当前阻塞：无。

## 已完成记录

- 上下文恢复机制已完成：新增本快照、更新 `resume_context.ps1` 默认读取路径和历史开关，并同步恢复文档与中文问题日志；本地脚本输出验证通过，默认不加载历史文件。
- M277 已完成并推送：`e0104b8 feat: expose composite runs over http`。
- M277 Docker 定向 16/16、compileall、architecture strict、CI/stage、生产 `/health/ready` 通过。
- M278 能力图、Spec、Plan 已创建；尚未提交，属于当前工作树变更。
- M278-C/D 已完成：Docker 定向生命周期 + HTTP **7/7**，覆盖 FastAPI/stdlib 路由与 SQLite 重启接管。
- 已安装 GitHub `sivaprasadreddy/sdd-skills` 的 `sdd-feature` 技能到 Codex 技能目录；该安装不修改项目仓库。

## 当前工作树变更

- `tasks/plan.md`
- `tasks/todo.md`
- `docs/m278-composite-lifecycle-capability-map.md`
- `docs/m278-composite-lifecycle-spec.md`
- `docs/m278-composite-lifecycle-plan.md`
- `tests/test_m278_composite_lifecycle.py`
- `tests/test_m278_composite_http.py`
- `agent/models.py`
- `agent/sqlite_store.py`
- `agent/application/async_runs.py`
- `agent/application/composite.py`
- `agent/application/composite_runs.py`
- `docs/agent-work-state.md`
- `scripts/resume_context.ps1`
- `docs/task-resume.md`
- `docs/agent-context-resume.md`
- `docs/agent-development-issues.md`
- 本快照机制已提交；M278 规划、实现和测试仍未完成。

## 最近任务记录

### 上下文恢复最小快照（已完成，待提交）

- 改动：用 `agent-work-state.md` 替代长恢复卡作为默认入口；默认只读当前快照，历史检索需显式 `-IncludeHistory`。
- 验证：`pwsh -NoProfile -File scripts/resume_context.ps1` 成功；`git diff --check` 通过。
- 结果：恢复输出包含当前 goal 摘要、M278 规划指针、最近任务、待修改文件、验证约定和下一步；未读取完整历史文件。
- 下一步：继续 M278-C HTTP semantic commands。

### M278-C/D HTTP 与重启恢复（已完成，待提交）

- 改动：补齐 FastAPI/stdlib Composite async/detail/observability/evidence 路由验收；增加失效 owner 的 SQLite orphan job 重启接管测试。
- 验证：Docker `python -m unittest tests.test_m278_composite_lifecycle tests.test_m278_composite_http -v` **7/7** 通过。
- 结果：跨入口语义一致；孤儿任务只被新实例 claim 一次，canonical Composite Result 可查询。
- 下一步：运行 M278 阶段级 Docker 集成、compileall、architecture strict、CI/stage 和生产 health。

## 本阶段验证约定

- Python、GIS、compileall 和架构检查只在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持精简、离线；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 读取本文件。
2. 只读取上面列出的 M278 Spec/Plan 和当前任务待修改文件。
3. 运行 M278 阶段级 Docker 集成门禁；若通过则更新里程碑/问题日志并提交推送。
4. 完成一个子任务后立即更新本文件，再更新 `tasks/todo.md`。
