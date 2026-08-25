# Agent 任务进度账本

> 这是上下文恢复用的短账本，不是完整历史。每个子任务开始、完成或暂停时追加/更新一条记录；只保留可恢复所需的目标、状态、文件、验证、阻塞和下一步。详细阶段结论放在对应 Spec/Plan、milestones 和中文问题日志中。

## 使用规则

- 新对话或上下文压缩后，恢复脚本只读取本账本最近记录，不全文加载历史。
- 进行中的任务必须列出“需要修改的文件”；完成后保留实际改动文件和验证结果。
- `tasks/task-state.md` 保留为兼容性的详细当前状态；两者冲突时，以本账本的最新记录为恢复指针，并在完成子任务时同步修正详细状态。
- 状态只使用：`进行中`、`已完成`、`已暂停`、`受阻`。
- 不记录 API key、prompt、模型原文、私有路径、完整原始数据或敏感异常。
- 阶段任务安排应覆盖更完整的依赖链，优先按能力切片集中完成契约、实现、集成和交付准备；避免把一个完整阶段拆成过多过小的任务。
- 验证只保留有独立失败模式的精简测试，并在相关实现集中完成后统一运行；跨入口契约、阶段级架构门禁和 readiness 保留，重复测试不重复运行。
- 本次 Goal 约束：每个阶段安排更完整的任务包，尽量一次覆盖契约、实现、集成、文档和交付；开发期间减少重复测试，阶段收口统一执行精简且有代表性的门禁。
- 新增约束：阶段任务应适度增多并覆盖同一能力链的连续依赖；测试按独立风险合并执行，不随任务数量线性增加测试轮次。

## 当前进行中

### M292-A：Planner 组件事实交接与可恢复澄清全局规划 — 进行中

- 目标：从全局七维度规划 Planner 选择后的组件事实交接、最小澄清和同一请求的可恢复续跑，不陷入 GIS/Economic 数据细节。
- 已创建：`docs/m292-component-fact-handoff-capability-map.md`、`docs/m292-component-fact-handoff-spec.md`、`docs/m292-component-fact-handoff-plan.md`。
- 验证：M291 已完成 Python 合并门禁 **46/46**、新增状态回归 **6/6**、Node projection smoke、compileall、architecture strict、readiness 200；M292 规划文档已完成。
- 阻塞：无。M291 live 的 `taskplan_component_clarification` 已转为可恢复澄清，未创建 run。
- 下一步：实现 M292-B 组件 requirements 与 Domain preview 的公共事实交接。

### M288-B/C/D/E：provider structured-output 能力协商与阶段交付 — 已完成

- 目标：建立 provider-neutral structured-output profile，接入 OpenAI-compatible Responses/Chat Completions wire mode，并让 Composite planning、持久化、live receipt 和前端 projection 保留同一份脱敏能力证据。
- 实际修改：`agent/provider_structured_output.py`、`agent/openai_config.py`、`agent/llm_planner.py`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`evaluation/live_provider_probe.py`、`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`、`tests/test_m288_wire_structured_output.py`。
- 结果：默认 strict `json_schema`；显式 `json_object` 仅改变 wire 请求，不放宽本地 schema/allowlist/TaskPlan 门控；`unavailable` 在 transport 前 fail closed；provider 来源、reason、status、error、attempts/retries 均有界且不含密钥。
- 验证：Docker M288 + M279 + M286 + M287 **25/25**；Docker compileall、architecture strict、生产 readiness 200、首页 200、Node projection smoke 通过；一次显式 live provider probe 为 `READY`、Chat Completions、`json_schema`、schema enforced、1 次请求 0 重试。
- 阻塞：无。真实 Composite 多组件输出仍按 M285/M287 证据保持严格门控，不能将 provider connectivity probe 误记为跨域执行成功。
- 下一步：完成 M288-E 文档/问题记录/提交推送，然后从全局七维度规划 M289 真实 Composite 成功/澄清/拒绝矩阵。

## 最近完成

### M290-A～E：Provider Deadline 与真实 Composite 完成 — 已完成

- 结果：完成 provider/harness deadline receipt、provider budget 上限、Composite Domain session 隔离、Domain workflow 复用和空组件 success 的安全拒绝；不创建孤儿 execution run。
- 文件：`agent/runtime_core/composite_taskplan.py`、`agent/composite_planner.py`、`agent/composite_request_context.py`、`agent/runtime.py`、`agent/service.py`、`domains/gis/domain.py`、`domains/economic/catalog.py`、`evaluation/live_provider_probe.py`、`scripts/live_provider_probe.py`、`tests/test_m290_provider_deadline_completion.py`。
- 验证：Docker M290/M282/M279/M289/M286/M287 集中 **41/41**，未重复发起 live；真实模型仍保持脱敏安全失败。
- 下一阶段：M291 处理 Planner 语义完整性和 capability → workflow → TaskPlan 闭合。

### M291-A～C：Planner 语义完整性与能力目录闭合 — 已完成

- 结果：新增 `spatial-agent.plan-completeness.v1`；目录为每个 capability 生成 task-plan/answer-only/unbound 绑定；Composite Planner 在 execution run 前拒绝空组件、重复组件、未绑定 workflow 和 deferred TaskPlan。
- 验证：新增 M291 5 项 compact contract，与 M290/M282/M279/M289/M286/M287 合并 **46/46**；compileall、architecture strict、readiness 200 通过。
- 下一步：M292 组件事实交接与可恢复澄清。

### M291-D/E：跨入口语义投影与阶段交付 — 已完成

- 结果：`plan_completeness` 沿 planning evidence、artifact/async safe projection、Composite View 和 Console projection 传播；新增“计划已验证/计划需要补充”用户摘要；组件事实不足统一显示为澄清。
- 文件：`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`、中文文档与恢复账本。
- 验证：Python 46/46、状态映射回归 6/6、Node smoke、compileall、architecture strict、readiness 200；一次真实 Composite live 结构化输出成功但 Domain preview 需要事实，未创建 run。
- 下一阶段：M292 组件事实交接与可恢复澄清。

### M289-B/C/D/E：真实 Composite Planner 纵向收口与阶段交付 — 已完成

- 结果：planning matrix、prepared plan sync/async seam、前端 structured-output 摘要和 safe live timeout receipt 已交付；M290 全局能力图/Spec/Plan 已创建。
- 验证：Docker M289/M280/M283 **15/15**、compileall、architecture strict、readiness 200、Node projection smoke 通过；版本待提交推送。

### M289-B/C/D：真实 Composite Planner 纵向收口 — 已完成

- 结果：planning outcome matrix、prepared plan sync/async 对照、artifact/restart 复用既有生命周期证据，前端合并并显示 structured-output 计划状态；真实 Composite timeout 保持 fail closed。
- 验证：Docker M289/M280/M283 **15/15**、compileall、architecture strict、readiness 200、Node projection smoke 通过；未保存模型原文或敏感配置。

### M289-B：Planner-to-TaskPlan 纵向 harness 与跨状态 evidence — 已完成

- 结果：新增领域中立 planning outcome matrix（最多 8 个 case），统一记录 success/clarification/rejection/failure、component count 和 `execution_run_created`；新增 prepared-plan acceptance seam，sync/async 复用同一 canonical request 和 planner evidence。
- 文件：`evaluation/composite_planning_matrix.py`、`scripts/m289_real_composite_acceptance.py`、`tests/test_m289_real_composite_success.py`、`evaluation/live_provider_probe.py`、`tests/test_m280_real_composite_acceptance.py`。
- 验证：Docker M289 + M280 **8/8**、compileall 通过；未知/非预期 run 创建会被 matrix 判失败；真实 Composite probe 45 秒 timeout 安全返回。

### M288-B/C/D：provider structured-output 能力协商与跨入口 evidence — 已完成

- 结果：profile、wire adapter、Composite planning evidence、async/artifact/restart 过滤、live receipt 和前端 projection 已接通；保持公共 client 两参数兼容接口，不把 provider 特殊字段扩散到 Domain/Runtime。
- 验证：阶段集中门禁 **25/25**，compileall、architecture strict、readiness/home 200、Node projection smoke 通过；live probe 仅记录脱敏模式和指标。
- 当前：进入 M288-E 阶段收口，尚未提交本阶段版本。

### Goal 执行节奏约束同步 — 已完成

- 结果：将“每阶段编排更完整的能力切片、减少微阶段；开发中只做必要检查、阶段收口统一精简验证”提升为项目 Goal 的正式执行约束。
- 文件：`docs/agent-project-direction.md`、`docs/agent-work-state.md`、`tasks/task-progress.md`。
- 验证：仅完成文档变更核对；本次没有运行重复业务测试。
- 后续：M285-E 仍按现有阶段计划推进，下一阶段以完整能力包规划，不按单个测试例拆分。

### M285-B：Planner entry policy 与 source evidence — 已完成

- 结果：统一记录 Rule/Replay/LLM 的 requested planner、selected source、选择状态、原因、候选能力数量和 selected capability ids；成功、澄清/拒绝、provider failure 均使用同一版本化 selection evidence。
- 文件：`agent/application/composite_planning.py`、`tests/test_m285_open_query_planner.py`。
- 验证：Docker 定向 M285 契约 **3/3** 通过；未改变 Runtime 生命周期或执行入口。

### M285-C/D：TaskPlan bridge 与跨入口证据 — 已完成

- 结果：新增领域中立 `CompositeTaskPlanBridge`；显式 replay TaskPlan 经过严格字段、DAG 依赖、工具 allowlist、结果类型和步数门控；旧候选安全 deferred。桥接投影接入 planner evidence，并沿 HTTP、async、artifact 和 restart 恢复。
- 文件：`agent/runtime_core/composite_taskplan.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_planner.py`、`tests/test_m285_open_query_planner.py`、`tests/test_m283_open_query_agent.py`、M285 Spec/Plan。
- 验证：Docker M285/M283 **13/13**、compileall、architecture strict、readiness 通过；两步 replay 与非法工具 fail closed，HTTP→async evidence 和 artifact/restart evidence 一致。
- 备注：真实中转 probe 已单独记录为 M285 live provider schema 阻塞，不影响离线 TaskPlan bridge 安全门控。

### M285-A：开放式 Planner 多工具编排全局规划 — 已完成

- 结果：从产品、架构、数据、模型、部署、体验和测试七个维度确定 M285 只补“开放式请求 → 已注册能力 → canonical TaskPlan/DAG → 统一 Runtime”的纵向成功切片，不新增专题数据、RAG、依赖或 Runtime 分支。
- 文件：`docs/m285-open-query-planner-capability-map.md`、`docs/m285-open-query-planner-spec.md`、`docs/m285-open-query-planner-plan.md`、`tasks/plan.md`、任务状态与工作快照。
- 验证：Spec/Plan 已定义 Rule/Replay/LLM parity、至少两步 replay、跨入口证据一致和显式 live 验收；M284 版本 `3a0857e` 已推送。

### M284-A：会话清空与空间上下文一致性规划 — 已完成

- 结果：完成七维度 capability map、Spec、Plan；确定不修改 Runtime、Planner、ToolRegistry、Result schema 或服务端会话语义。
- 文件：`docs/m284-session-reset-consistency-capability-map.md`、`docs/m284-session-reset-consistency-spec.md`、`docs/m284-session-reset-consistency-plan.md`、任务状态与工作快照。
- 验证：规划边界与 M283 已知地图 smoke 失败证据一致；实现按 reset-boundary → stale-render-guard → reset-acceptance 串行执行。

### M284-B/C：reset boundary 与 stale-render guard — 已完成

- 结果：RendererRegistry 提供有界 reset context 和 generation 失效；GIS adapter 清理地图实例、视觉 surface、selection 和按钮；Console 的清空、切换会话/领域复用 reset boundary，并阻止旧异步 render 回写。
- 文件：`web/src/console_renderer_registry.js`、`web/src/console_gis_plugin.js`、`web/src/console_app.js`、`scripts/console_reset_contract_smoke.js`。
- 验证：Node reset contract、plugin renderer regression、四个前端脚本语法检查通过；Docker compileall 和 architecture strict 已通过。
- 阻塞：无。

### M284-D：精简 reset 与地图浏览器回归 — 已完成

- 结果：地图 smoke 等待 Console bootstrap/domain readiness，并先建立空白会话边界，避免初始化历史异步恢复覆盖测试 fixture；覆盖选择、清空即时状态和延迟状态。
- 文件：`scripts/console_map_smoke.js`。
- 验证：Docker Node reset/plugin/projection smoke 通过；浏览器 map smoke 通过（Leaflet 图层 1、SVG 路径 4、selection 清空通过）。
- 阻塞：无。

### M283-F：文档、版本交付与全局重规划 — 已完成

- 结果：完成阶段文档、中文问题日志、恢复快照与短账本收口；恢复脚本已验证显示当前快照和 M283-E/D，而不是旧历史记录。
- 版本：`4d022f4` 已提交并推送到 `origin/main`。
- 下一步：新的阶段先做全局规划；地图清空后的空间上下文复位作为候选问题，不在本阶段伪装成已修复。

### M283-E：真实与跨入口验收 — 已完成

- 结果：完成精简 Docker/HTTP/readiness/browser 验收，并完成 1 条真实模型 + local GIS 成功 case；Provider 失败/澄清/拒绝仍由既有契约安全处理。
- 验证：Docker M283 **7/7**、compileall、architecture strict、readiness/resource **200**、Node/Docker/browser projection smoke 通过；live case `COMPLETED`，1 次请求、0 重试。
- 已知问题：既有地图 smoke 的清空复位问题已记录，未隐瞒为绿色结果。

### M283-D：动态结果体验与阶段里程碑 — 已完成

- 结果：新增 `ConsoleResultProjection`，将 context、plan、clarification、answer、view、evidence 汇总为结论优先的阶段投影；未知领域/工具仍走通用 renderer。
- 文件：`agent/web_assets.py`、`web/src/console_result_projection.js`、`web/src/console_app.js`、`web/src/index.html`、`web/src/styles.css`、`scripts/console_result_projection_smoke.js`、`scripts/console_result_projection_browser_smoke.js`。
- 验证：Node smoke、Docker 内 Node smoke、资源 200、生产 readiness 200、浏览器 projection smoke 通过；地图 smoke 因既有清空复位问题失败，已单独记录。

### M282-A：开放式请求能力图、Spec、Plan — 已完成

- 结果：建立 `request-context → capability-matching → planner-gateway → open-query-acceptance` 的阶段拆分，明确 v2 context、边界和精简 Docker 验收路径。
- 文件：`docs/m282-open-query-resolution-capability-map.md`、`docs/m282-open-query-resolution-spec.md`、`docs/m282-open-query-resolution-plan.md`、`tasks/plan.md`、`tasks/todo.md`。
- 验证：Spec/Plan 与当前 Goal 边界一致；未执行运行时代码测试。

### M281-E：动态 Composite 结果体验与跨入口一致性 — 已完成

- 结果：新增 `spatial-agent.composite-view.v1`、`/composite-runs/{run_id}/view` 和前端动态 Composite View；版本 `a2b240c` 已推送。
- 验证：Docker 19/19、compileall、architecture strict、JS/browser smoke 通过。

### M282-B：Context contract 与 RequestFacts 聚合 — 已完成

- 结果：新增 `spatial-agent.composite-request-context.v2` builder；聚合多 Domain facts、discovery、catalog、workflow、data readiness 和有界 clarification，生成稳定 fingerprint；接入 `CompositePlanningApplication`，保留 planner context 与 evidence 指纹。
- 安全：事实提取/发现失败结构化降级；能力必须来自 catalog；未知能力、不可用能力不会进入 execution；敏感键和 JSON 字节预算过滤。
- 文件：`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`tests/test_m282_open_query_resolution.py`、恢复/goal 文档与任务账本。
- 验证：Docker M282/M279/M281 **20/20**；真实生产 Rule/本地上下文探测返回 `NEEDS_CLARIFICATION` 且 context schema 为 v2；compileall、architecture strict 通过。

### M282-C：Capability matching、缺失事实与结构化澄清 — 已完成

- 结果：候选能力缺失字段只依据已选/唯一候选投影，避免多候选必填条件求并集；发现失败、全部候选不可用、未知能力和上下文超限均结构化 fail closed；HTTP semantic command 保留同一 context clarification。
- 文件：`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`tests/test_m282_open_query_resolution.py`。
- 验证：Docker M282/M279/M281 **24/24**；compileall、architecture strict 和恢复脚本最小读取验证通过。

### M282-D：Planner gateway 与跨入口一致性 — 已完成

- 结果：Rule/LLM Planner 接受同一 v2 context 并共享 canonical plan/allowlist；HTTP semantic command 保留 context、clarification 和 evidence 指纹；未知 context schema 在 provider 调用前拒绝。
- 文件：`agent/composite_planner.py`、`agent/application/composite_planning.py`、`tests/test_m282_open_query_resolution.py`。
- 验证：Docker M282 定向 **9/9**，M278 生命周期/HTTP **7/7**；联合回归 16/16，compileall、architecture strict 通过。

### M282-E：阶段验收、文档与版本交付 — 已完成

- 结果：完成 Docker readiness/HTTP、阶段 Spec/Plan、milestones、中文问题日志、恢复快照和任务账本收口；真实模型短探测安全拒绝非法 Planner 输出，未创建 run。
- 验证：Docker M282/M279/M281 **24/24**、M278 **7/7**；compileall、architecture strict、恢复脚本最小读取、生产 `/health/ready` HTTP 200 通过。
- 版本：`a7e933b` 已提交并推送到 `origin/main`。

### M283-A：全局能力图、Spec、Plan — 已完成

- 结果：从产品、架构、数据、模型、部署、体验、测试七个维度规划开放式成功链路、Provider 门禁、动态结果体验和显式真实验收；不增加专题硬编码。
- 文件：`docs/m283-open-query-agent-capability-map.md`、`docs/m283-open-query-agent-spec.md`、`docs/m283-open-query-agent-plan.md`、`tasks/task-progress.md`、`docs/agent-work-state.md`。
- 验证：已推送 M282 版本 `a7e933b`；M283 进入 B。

### M283-B：Planner gateway 收口 — 已完成

- 结果：新增 `ReplayCompositePlanner`，与 Rule/LLM 复用同一 provider normalization、context schema 校验、canonical plan 和 capability allowlist；支持脱敏 alias replay，不保存模型原文。
- 文件：`agent/composite_planner.py`、`tests/test_m283_open_query_agent.py`。
- 验证：Docker M283/M282/M279 **23/23**；documented alias、未知字段、replay failure 和 v2 context parity 通过。

### M283-C：开放式成功切片与跨入口恢复 — 已完成

- 结果：`CompositePlanningApplication` 通过可选 planning-evidence seam 进入同步/异步 Composite lifecycle；有界 planner evidence 可恢复到 result、evidence、artifact 和 SQLite/restart，不把完整 v2 context 写入执行请求。
- 文件：`agent/application/composite_runs.py`、`agent/application/composite_planning.py`、`tests/test_m283_open_query_agent.py`。
- 验证：Docker M283/M278/M282 **23/23**；HTTP semantic Replay submission、async artifact/restart evidence、M278 lifecycle/HTTP、M282 回归通过；compileall、architecture strict 通过。

## 记录模板

```text
### <任务 ID>：<名称> — <状态>
- 目标：
- 需要修改/实际修改：
- 验证：
- 阻塞：
- 下一步：
```
