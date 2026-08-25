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

- 阶段：M280 真实跨域 Composite 纵向验收。
- 状态：M279 已提交推送；M280 Spec/Plan/能力图已创建，准备实现 M280-A Response compatibility。
- 阶段规划：
  - [`docs/m280-real-composite-acceptance-capability-map.md`](m280-real-composite-acceptance-capability-map.md)
  - [`docs/m280-real-composite-acceptance-spec.md`](m280-real-composite-acceptance-spec.md)
  - [`docs/m280-real-composite-acceptance-plan.md`](m280-real-composite-acceptance-plan.md)
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

### M279-A Catalog projection（待开始）

- 目标：把已登记 Domain 的 capability/workflow/result/data readiness 投影为 Planner 可消费的领域中立上下文。
- 待读/待修改文件：
  - `agent/domain_runtime_host.py`
  - `agent/application/catalog.py`
  - `agent/domain_catalog.py`
  - `agent/application/composite_planning.py`（新增）
  - `tests/test_m279_composite_planner.py`（新增）
- 验证：先用 fake Domain/catalog 验证 allowlist、字段预算和敏感字段过滤；暂不调用真实模型。
- 当前阻塞：无。

### M279-A Catalog projection（已完成）

- 改动：新增 `agent/application/composite_planning.py` 的 `CompositeCapabilityProjector`；从 `DomainRuntimeHost`/Service 公开 seam 投影跨 Domain capability、workflow、result、dataset readiness 和 bounded index。
- 安全边界：只保留 allowlisted 字段、工具名、结果类型、请求事实声明和 workflow 步骤身份；过滤 source path、私密 payload 和 workflow args；限制 Domain/能力/workflow/context 大小。
- 验证：Docker `tests.test_m279_composite_planner` **3/3** 通过，覆盖跨 Domain 合并、readiness、字段过滤、未知 Domain 拒绝和预算。
- 结果：Planner 可消费的上下文仍与执行/Domain 内部实现分离；不创建执行 run、不调用模型。
- 下一步：M279-B 定义 Rule/LLM 共同的 bounded Composite plan contract。

### M279-B Rule/LLM Composite Planner contract（已完成）

- 改动：新增 `agent/composite_planner.py`，定义 `composite_plan_schema()`、Rule/LLM planner adapter 和 canonical candidate normalization；成功输出转换为现有 `spatial-agent.composite-request.v1`，保留 capability metadata 只作为规划投影。
- 安全边界：统一校验 outcome、组件字段、依赖和能力 allowlist；provider/规则异常只返回有界错误码，不保存或回传模型原文。
- 验证：Docker `tests.test_m279_composite_planner` **6/6** 通过，覆盖 Rule/LLM fingerprint 一致、澄清、非法字段、provider failure、上下文能力校验。
- 结果：Planner 只产生候选计划，不执行组件；合法计划可直接进入下一步 Application。
- 下一步：M279-C 实现 resolve → plan → validate/repair → clarify/submit。

### M279-C Planning Application（已完成）

- 改动：`CompositePlanningApplication` 实现 resolve catalog、plan、canonical request 校验、有限 repair lineage、clarification/rejection 和 M278 async/sync submit。
- 验证：Docker M279 定向测试覆盖 planning-only、不创建 run 的澄清、合法 canonical submit；与 M278 lifecycle 联合通过。
- 结果：Planner 与 Composite lifecycle 仍是两个可替换 seam，非法候选不会进入 coordinator。
- 下一步：M279-D 接入 HTTPApplication 与 FastAPI/stdlib `/composite-plans`。

### M279-D Shared HTTP planning command（已完成）

- 改动：`HTTPApplication` 增加 `composite_plan` 语义命令；FastAPI 与 stdlib 增加 `/composite-plans` URL 胶水；composition root 按 `planner=openai` 懒加载真实 OpenAI-compatible Planner，规则模式明确澄清不猜测组合。
- 验证：Docker M279 **10/10**，覆盖 semantic command、FastAPI/stdlib 路由一致性、M278 回归；compileall、architecture strict 通过。生产实际规则请求返回 `NEEDS_CLARIFICATION` 且不创建 run。
- 当前阻塞：无。
- 下一步：阶段级 CI/stage、真实容器 health 和显式一次真实模型 Composite planning 验收；默认 CI 不联网。

### M279-E 阶段验收与交付（已完成）

- 验证：Docker M279 + M278/M277/M256/M275/M276 **33/33**；CI/stage、compileall、architecture strict 通过；重建生产容器 `/health/ready` 为 `ready`。
- 实测：规则 `/composite-plans` 返回 `NEEDS_CLARIFICATION` 且无 `run_id`；真实中转模型规划请求 HTTP 200，但模型输出 `plan_outcome_invalid`，系统安全返回 `REJECTED`，未创建 execution run。
- 结果：provider 可达与 Planner contract 失败已分层；未把模型异常伪装成成功，也未触发 GIS/Economic 执行。
- 当前阻塞：无。真实模型的输出契约兼容性留作后续 provider/Planner 优化，不阻塞离线阶段交付。

### M280-A Response compatibility（待开始）

- 目标：对真实中转模型的有限旧式/省略字段输出做显式归一化，最终仍进入 M279 canonical plan contract。
- 待读/待修改文件：
  - `agent/composite_planner.py`
  - `agent/application/composite_planning.py`
  - `tests/test_m280_real_composite_acceptance.py`（新增）
- 验证：先用 replay/fake 覆盖合法别名、缺少 outcome、未知字段、provider error；不调用网络。
- 当前阻塞：无。

## 已完成记录

- 上下文恢复机制已完成：新增本快照、更新 `resume_context.ps1` 默认读取路径和历史开关，并同步恢复文档与中文问题日志；本地脚本输出验证通过，默认不加载历史文件。
- M277 已完成并推送：`e0104b8 feat: expose composite runs over http`。
- M277 Docker 定向 16/16、compileall、architecture strict、CI/stage、生产 `/health/ready` 通过。
- M278 能力图、Spec、Plan 已创建并推送；提交为 `b49630a`。
- M278-C/D 已完成：Docker 定向生命周期 + HTTP **7/7**，覆盖 FastAPI/stdlib 路由与 SQLite 重启接管；阶段级联合 **23/23**、compileall、architecture strict、CI/stage、生产 health 和真实 Docker async/evidence 验收通过。
- M279 Spec/Plan/能力图已创建；下一步实现 Catalog projection，不读取无关历史或全量 Domain 源码。
- M279-A/B/C/D/E 已完成：Docker 定向 **10/10**、阶段级联合 **33/33**；新增 projector、Rule/LLM contract、Planning Application 与 `/composite-plans` 跨入口 semantic route；真实中转规划失败按 contract 结构化拒绝。
- M279 已提交并推送：`c351fe3 feat: add natural language composite planner`。
- M280 Spec/Plan/能力图已创建；下一步只读取 M280 规划和 M280-A 文件，先实现 response compatibility。
- 已安装 GitHub `sivaprasadreddy/sdd-skills` 的 `sdd-feature` 技能到 Codex 技能目录；该安装不修改项目仓库。

## 当前工作树变更

- `docs/agent-project-direction.md`
- `docs/agent-work-state.md`
- `docs/m279-composite-planner-capability-map.md`
- `docs/m279-composite-planner-spec.md`
- `docs/m279-composite-planner-plan.md`
- `agent/application/composite_planning.py`
- `tests/test_m279_composite_planner.py`
- `agent/composite_planner.py`
- `agent/application/composite_planning.py`
- `agent/application/http.py`
- `production_api.py`
- `serve_api.py`
- `tests/test_m279_composite_planner.py`
- `docs/agent-project-direction.md`
- `docs/agent-development-issues.md`
- `docs/agent-context-resume.md`
- `docs/milestones.md`
- `docs/m280-real-composite-acceptance-capability-map.md`
- `docs/m280-real-composite-acceptance-spec.md`
- `docs/m280-real-composite-acceptance-plan.md`
- `tasks/plan.md`
- `tasks/todo.md`
- M278 源码、测试和历史文档已提交；当前只保留 M279 规划与快照改动。

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
- 下一步：M278 已完成并推送；开始 M279-A Catalog projection。

### M278 阶段收口（已完成，已提交推送）

- 改动：Composite canonical envelope、可恢复 run application、HTTP async/detail/observability/evidence 语义命令、FastAPI/stdlib 路由、artifact/SQLite/restart 测试和中文记录。
- 验证：M278 + M277/M256/M275/M276 **23/23**；compileall、architecture strict、CI/stage、生产 `/health/ready` 200；真实 Docker async run 的 detail 为 `composite_result`，artifact/evidence 可用。
- 结果：提交 `b49630a feat: add recoverable composite lifecycle` 已推送 `origin/main`。
- 下一步：M279-A 建立 Planner-facing cross-Domain catalog projection。

## 本阶段验证约定

- Python、GIS、compileall 和架构检查只在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持精简、离线；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 读取本文件。
2. 只读取上面列出的 M279 Spec/Plan 和 M279-E 待修改文件。
3. 只读取上面列出的 M280 Spec/Plan 和 M280-A 待修改文件，开始 response compatibility 的红→绿测试循环。
4. 完成一个子任务后立即更新本文件，再更新 `tasks/todo.md`。
