# Agent 当前工作快照

> 新对话或上下文压缩后的唯一默认交接入口。先读本文件顶部短快照，再读 [`tasks/task-progress.md`](../tasks/task-progress.md) 的“当前进行中/最近完成”有界区块；不要自动读取完整历史、全量源码、全量测试、模型响应或敏感配置。

## Goal 摘要（精简版）

建设 Agent Runtime 的实时交互与可观测体验：用户提交开放式问题后，持续看到真实的阶段进展、工具状态、可审计摘要和最终答案流，并能在断线、重启或失败后恢复。GIS 只是业务载体，不为单一区域、单一问句或单一数据集增加硬编码流程。

本阶段聚焦版本化 `RunEvent`、SSE/断线与重启恢复、polling fallback、真实模型的校验后答案流、前端分层结果展示，以及取消/重试/恢复。CLI、HTTP、前端和恢复流程共享事件、结果与证据契约；不展示隐藏思维链、Prompt、模型原文或敏感信息。

## Goal 附加约束：低成本上下文恢复

- 恢复只读取本快照、当前阶段 Spec/Plan、任务账本中最近的进行中任务，以及该任务明确列出的待修改文件。
- 只读取当前任务必需的文件；历史文档、milestones、归档、全量源码、全量测试、模型原文和敏感配置按需读取。
- 每个子任务开始、完成或暂停时更新 `tasks/task-progress.md`；阶段收口再同步任务状态、快照和历史恢复卡。
- 阶段任务按完整能力切片编排，测试按独立失败模式合并到阶段收口，不因每个小改动重复执行相同测试。

## 当前阶段

- 阶段：M315 聊天区实时答案占位与逐字收敛（已完成）
- 状态：右侧对话已接入实时答案气泡；规划/执行期间显示点状等待，收到答案事件后复用同一气泡逐字输出，完成后绑定运行详情且不重复追加。
- 当前任务：M315 已完成待提交；不要重复真实模型调用，下一阶段需基于全局目标重新规划。
- 协作方式：单 Agent 顺序开发，最大并发度为 1；不启动并行子代理。长期记忆以本快照、任务账本和当前阶段 Spec/Plan 为权威，避免 Provider 限流和共享工作树冲突。
- 阶段规划：
  - [`docs/m313-realtime-agent-experience-capability-map.md`](m313-realtime-agent-experience-capability-map.md)
  - [`docs/m313-realtime-agent-experience-spec.md`](m313-realtime-agent-experience-spec.md)
  - [`docs/m313-realtime-agent-experience-plan.md`](m313-realtime-agent-experience-plan.md)
  - [`docs/m314-live-model-stream-acceptance-spec.md`](m314-live-model-stream-acceptance-spec.md)
  - [`docs/m314-live-model-stream-acceptance-plan.md`](m314-live-model-stream-acceptance-plan.md)

## 当前任务明确文件

- `docs/m313-realtime-agent-experience-capability-map.md`
- `docs/m313-realtime-agent-experience-spec.md`
- `docs/m313-realtime-agent-experience-plan.md`
- `agent/run_events.py`
- `agent/runtime_state.py`
- `agent/sqlite_store.py`
- `agent/service_state.py`
- `agent/runtime_core/run_lifecycle.py`
- `agent/runtime.py`
- `agent/application/http.py`
- `production_api.py`
- `serve_api.py`
- `web/src/console_app.js`
- `web/src/index.html`
- `web/src/styles.css`
- `tests/test_m313_realtime_events.py`
- `tests/test_m16_openai_config.py`
- `agent/openai_config.py`
- `agent/runtime_factory.py`
- `agent/llm_planner.py`
- `agent/plan_schema.py`
- `web/src/console_run_events.js`
- `scripts/console_run_events_smoke.js`
- `web/src/console_answer_stream.js`
- `scripts/console_answer_stream_smoke.js`
- `agent/web_assets.py`
- `scripts/console_existing_run_browser_acceptance.js`

> 当前阶段按 Spec → Plan → 实现推进；若实现发现直接依赖，再把文件加入清单，
> 避免恢复上下文时读取无关文件。

## M313 阶段验收摘要

- Docker M313 事件与答案流契约：**11/11**；Node 实时事件 smoke：通过；生产验收：通过。
- Domain SSE：真实运行产生 **81** 个事件，其中 **51** 个 `answer_delta`；`Last-Event-ID: 1` 从第 2 个事件续传。
- 重启恢复：服务重启后同一 run 仍可读取第 2～13 个事件；readiness **200**。
- 浏览器：动态加载 `spatial_overview_result` 的 `overview/map`，地图真实路径 **1** 条、轨迹 **11** 项、无错误。
- 真实模型 + 本地 GIS：最终结果为 `live_model`，`answer_streaming=true`；不保存密钥、Prompt 或模型原文。
- 后续修复：真实模型已有 run 产生 73 个事件、57 个 `answer_delta`，前端通过 `ConsoleAnswerStream` 在终态前逐字符消费；未重复调用模型。
- 后续修复：规划阶段超过 12 秒会显示“模型响应较慢，仍在等待返回”及累计耗时；本次用户 Run 的安全失败证据为 planning/provider_timeout，终态事件完整。
- M314 当前验收：真实 Provider 探测 `READY`，真实 DeepSeek + 本地 GIS 最小回答 `COMPLETED`，1 次规划请求、0 重试；该 Run 产生 384 个事件、368 个 `answer_delta`，SSE 与 `Last-Event-ID: 1` 续传均完整。
- M314 修复：SSE 只在当前页含终态事件时关闭；跨页终态不再因 100 条分页上限丢失。新增 `page_contains_terminal_event()` 公共契约。
- M314 效率：规划与答案使用独立 provider 预算；答案默认 20 秒、768 token、0 重试，可由 `OPENAI_ANSWER_*` 覆盖；不改变规划、工具和结果校验。
- M314 补充修复：当 OpenAI 兼容 Provider 返回 `invalid_model_response`（本次实测输出 token 恰好达到 2048 上限）时，Planner 只进行一次紧凑计划恢复；恢复计划仍经过 TaskPlan、工具和执行绑定校验，并在 metrics 记录 `compact_recovery_attempts`。
- M315：右侧对话新增“正在生成答案 · / ·· / ···”占位动效；首个 `answer_delta` 到达后移除占位并复用同一气泡逐字显示，终态只收敛现有消息；支持 `prefers-reduced-motion`。

## 阶段完成后的全局重规划指针

- 产品：实时进展已可见，下一步应降低技术信息噪声，强化面向用户的结论、解释和恢复操作。
- 架构：保持 RunEvent/Result/View/Evidence 单一契约，下一阶段不重复建设 Runtime 生命周期。
- 数据/GIS：继续扩展可登记数据能力与健康证据，但不把单一数据集写成系统分支。
- 模型：保留结构化计划校验与答案流，继续记录延迟、降级和可替换 provider 证据。
- 部署：Docker 已成为 GIS/live 验收环境，继续保持默认离线门禁和显式 live 验收。
- 体验：候选方向为 React 增量迁移，复用现有实时事件与动态结果视图契约。
- 测试：维持单 Agent、精简风险分层；只增加能够证明新边界的契约或浏览器验收。
- 下一阶段候选：M314 React Console 增量迁移与实时契约复用；创建新 Goal 前需另行形成 capability map、Spec 和 Plan。

## M311：通用分析意图与跨域开放链路 — 已完成

- 新增 `spatial-agent.analysis-intent.v1`，接入 Domain facts、Capability Catalog、
  Planner Envelope、Composite View、异步/artifact evidence 和 Console projection。
- 正常 LLM 工具计划强制声明 `output.type`，缺失时在执行前 fail closed，避免实际步骤
  成功却被包装为 `unknown` Result。
- Docker M311 **13/13**、M2 **17/17**、M310 **14/14**、M309 **8/8**，compileall、
  architecture strict、Node projection、Service smoke、跨入口 identity、真实本地 GIS
  HTTP 和 readiness **200** 通过；一次真实模型调用到达 provider 并完成真实 GIS 执行。
- 本阶段不重复调用模型；未保存密钥、prompt、模型原文或私有原始数据。

## M310：开放请求能力选择与数据语义闭合 — 已完成

- 结果：统一 `any/all/one` 事实需求语义，闭合 capability → Domain workflow →
  TaskPlan/DAG → ToolRegistry → execution binding；新增领域中立 readiness 和有界
  `planning_failure` 投影，区分澄清、预览失败、绑定失败和拒绝。
- 前端：结构化结果投影能够显示等待补充、计划未生成和计划校验未通过，不显示内部
  错误码、工具名、prompt 或 provider 原文；修复 planning failure 阶段条件的字段
  命名/逻辑运算符问题。
- 验证：Docker M310 **14/14**、M309 相邻回归 **8/8**、compileall、architecture
  strict、Node projection、Service smoke、跨入口 identity、真实本地 GIS HTTP 和
  `/health/ready` 200 通过。
- 真实模型：唯一一次显式调用使用结构化输出通道并到达 provider，返回
  `NEEDS_CLARIFICATION`，未创建执行 run；按真实语义澄清记录。

## M308-F：开放组合纵向链路与用户答案质量 — 已完成

- 结果：真实 GIS/Economic/Indicators 三组件完成规划和执行；答案契约增加可选 `next_steps`；上下文 workflow 约束漂移与 handoff 无条件合并问题已修复。
- 验证：Docker M308/相邻 Composite **28/28**，真实组合与跨入口验收通过；compileall、architecture strict、Node projection、Service smoke、生产 HTTP acceptance 和 readiness **200/ready**。
- 交付准备：阶段文档已补齐，下一阶段 M309 文档已创建；本次工作区待统一提交并推送。

## M309-A：模型计划结果矩阵与全局基线 — 已完成

- 目标：以 M308 的 3+ 组件闭环为基线，冻结 provider-backed 成功、澄清、非法计划、有限修复、provider failure 和执行失败的公共状态与 run 创建边界。
- 边界：只使用现有 Planner Envelope、Capability Catalog、TaskPlan/DAG、ToolRegistry、workflow、execution binding 和 Result/Evidence seam，不新增专题工具或领域专用前端分支。
- 结果：planner-attempt 对无 metrics 客户端也能记录真实调用状态和 retryable；provider failure、语义拒绝和澄清保持独立状态。
- 验证：Docker M309-A 精简契约 **4/4** 通过；阶段门禁仍在 M309-E 集中执行，真实模型最多显式调用一次。
- 阻塞：无。

## M309-B：真实模型到可执行计划的受控闭合 — 已完成

- 目标：让多目标开放请求通过 Capability Catalog 形成多个已登记组件，并在 schema、canonical DAG、TaskPlan、ToolRegistry、workflow 和 execution binding 全部门禁通过后执行。
- 结果：模型提示补充通用多目标拆分原则；3+ 组件输出继续经过 catalog/schema/canonical DAG/TaskPlan/ToolRegistry/workflow/execution binding 全部门禁。
- 验证：Docker M309-A/B 相关契约与 M305/M287 相邻回归 **18/18** 通过；未执行真实模型。
- 边界：有限 repair 最多一次；不得用 Rule/Replay 静默替代真实模型失败，不得放宽执行授权。
- 阻塞：无。

## M309-C：默认 Agent 的可感知体验 — 已完成

- 目标：结构化答案对象只投影可读文本；失败提示按公共错误平面生成；阶段状态、限制和下一步继续由 Result/View/Evidence 驱动。
- 结果：聊天摘要安全读取 `summary/headline` 或明确字符串；拒绝、规划失败和执行失败提示通用化，不展示内部对象字段。
- 验证：Docker 前端构建与 Node Console Result Projection smoke 通过。
- 阻塞：无。

## M309-D：跨入口恢复与一致性 — 已完成

- 目标：确认 M309 的 planner receipt、默认答案和阶段投影不改变同步、异步、HTTP、View、artifact、SQLite/restart 的公共 identity。
- 结果：Docker 三组件跨入口验收六项 identity 对照全部为 `true`，artifact 可用，View answer 保留 `next_steps` 字段。
- 验证：`scripts/m308_cross_entry_acceptance.py` 通过；未执行额外真实模型请求。
- 阻塞：无。

## M309-E/F：阶段验收、文档与版本交付 — 已完成

- 阶段门禁：重建 Docker 镜像并强制重建服务后，M309/M308/M303/M305 精简契约 **31/31**，compileall、architecture strict、Node projection、Service smoke、跨入口验收、真实 GIS 三组件验收和生产 HTTP acceptance 全部通过；`/health/ready` 为 `ready`。
- 真实模型：唯一一次调用在修复前返回结构化计划，但 GIS `raster_metadata` preview 因缺少 `dataset` 事实失败；未创建 execution run。修复后的成功由脱敏 Replay 和真实 Docker GIS 验收证明，不冒充 live 成功。
- 交付：中文问题日志、M309 Plan、恢复快照、任务账本和 M310 能力图/Spec/Plan 已同步；本次版本提交后推送。

## M310-A：事实需求矩阵与基数语义 — 已完成

- 目标：冻结 `any/all/one` 事实需求语义及缺失、歧义、ready、unavailable 的公共投影；不改变 Runtime、Planner、ToolRegistry 的执行授权边界。
- 当前文件：`agent/capability_catalog.py`、`agent/runtime_core/component_fact_handoff.py`、`agent/composite_request_context.py`、`tests/test_m310_open_request_capability_closure.py`。
- 阻塞：无。

## M310-B：Capability 到 Domain workflow 闭合 — 已完成

- 结果：选中 capability 的 workflow 必须由 Domain resolver 确认，不能从 context workflow 兜底；workflow 身份不完整或不属于 capability 时在 preview 前终止；不可用与未绑定 capability 保持不同状态。
- 文件：`agent/runtime_core/composite_taskplan.py`、`tests/test_m310_open_request_capability_closure.py` 及 M310-A 公共 requirements 投影文件。
- 验证：Docker M310-B **10/10**；未执行真实模型。
- 下一步：进入 M310-C，统一 TaskPlan 物化和失败分类。

## M310-C：TaskPlan 物化与失败分类 — 已完成

- 目标：复用已有 TaskPlan/DAG、ToolRegistry 和 execution binding 门禁，统一 clarification、preview invalid/failed 和 binding failed 的 public evidence 与 run 创建边界。
- 当前文件：`agent/application/composite_planning.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`、`tests/test_m310_open_request_capability_closure.py`。
- 验证：开发期间只运行新增或直接相关契约；阶段收口在 Docker 集中执行，并包含一次显式真实模型验收。
- 阻塞：无。

## M310-D：数据 readiness 与结果证据 — 已完成

- 目标：将 capability 的字段、空间/时间对齐、覆盖范围和来源状态投影为明确 readiness，并保持事实、限制和结果证据一致。
- 结果：规划失败返回有界 `planning_failure`，区分 clarification、preview_invalid、preview_failed、binding_failed 和 rejected；通用 `failure.v1` 同步保留，非 `PLANNED` 状态不创建 execution run。
- 当前文件：`agent/capability_catalog.py`、`agent/runtime_core/analysis_discovery.py`、`agent/composite_request_context.py`、`agent/composite_view.py`、`tests/test_m310_open_request_capability_closure.py`。
- 验证：开发期间仅运行新增或直接相关契约；阶段收口在 Docker 集中执行，并包含一次显式真实模型验收。
- 阻塞：无。

## 验证与安全约定

- Python、GIS、compileall、架构检查统一在 Docker 中运行：
  `docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent ...`
- 默认测试保持离线精简；真实模型、真实 GIS、Docker HTTP 和浏览器只做显式验收。
- 不读取、输出或提交 API key、`.env.production`、模型原文、真实原始数据或宿主机私有路径。

## 恢复后的最小动作

1. 只读取本文件顶部快照。
2. 只读取 `tasks/task-progress.md` 的当前进行中和最近完成有界区块。
3. 按当前任务记录读取对应阶段 Spec/Plan 及明确列出的源码/测试文件。
4. 完成或暂停子任务后先更新 `tasks/task-progress.md`，再同步本快照；兼容状态文件按需更新。
