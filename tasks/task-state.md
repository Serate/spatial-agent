# 当前任务状态账本

> 上下文恢复时只读取本账本的当前阶段和最近记录。历史阶段结论在对应 Spec/Plan、milestones 和中文问题日志中；不要把本文件重新扩展成完整历史。

> Goal 执行节奏补充：阶段按更完整的能力切片编排，尽量合并契约、实现、集成、文档和交付准备；开发中减少重复测试，阶段收口集中执行精简且有代表性的门禁。

## 当前阶段

- 阶段：M294 已验证计划到执行/答案/证据闭合
- 阶段规划：
  - `docs/m294-planned-execution-result-closure-capability-map.md`
  - `docs/m294-planned-execution-result-closure-spec.md`
  - `docs/m294-planned-execution-result-closure-plan.md`
- 执行方式：串行；默认测试离线精简；真实模型、GIS、Docker 和浏览器只做显式验收

### M295-A：全局开放式分析与数据发现闭环（进行中）

- 目标：在 M294 execution binding 之上，建立领域中立 discovery receipt，让开放式请求先完成能力/数据需求发现，再进入澄清或 validated TaskPlan。
- 规划：`docs/m295-global-open-analysis-discovery-capability-map.md`、`docs/m295-global-open-analysis-discovery-spec.md`、`docs/m295-global-open-analysis-discovery-plan.md`。
- 文件：当前先读取上述三个规划文件和 `agent/composite_request_context.py`、`agent/runtime_core/component_fact_handoff.py`、`agent/runtime_core/clarification_continuation.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`tests/test_m295_open_analysis_discovery.py`。
- 验证：M294 阶段已集中通过 Docker M294/M293/M291/M285/M281 **25/25**、真实 GIS binding、compileall、architecture strict、readiness 200；M295 实现期间只做必要局部检查，B～D 完成后统一测试。
- 阻塞：无。不得新增区域、指标或固定问句分支；不得绕过 execution binding。

### M294-A～E：已验证计划到执行/答案/证据闭合（已完成）

- 目标：建立领域中立 `execution-binding.v1`，将 validated TaskPlan/DAG 绑定为 Composite coordinator 的唯一执行输入，并统一跨入口结果、答案、View、Artifact、SQLite/restart 和 Evidence identity。
- 文件：`agent/runtime_core/execution_binding.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/run_lifecycle.py`、`agent/runtime.py`、`agent/service.py`、`agent/application/submission.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/application/composite.py`、`agent/composite_contract.py`、`agent/composite_view.py`、`agent/contract_versions.py`、`production_api.py`、`serve_api.py`、`tests/test_m294_execution_binding_closure.py`。
- 结果：执行前拒绝 binding/request/组件/计划/DAG/工具/结果类型漂移；Domain Runtime 直接消费 validated plan；公开投影和 artifact 不暴露完整参数；可选结构化答案生成与安全 fallback 已接入。
- 验证：Docker M294 compact + M293/M291/M285/M281 **25/25**；真实 GIS Service binding 验收通过；compileall、architecture strict、readiness 200 通过。
- 阻塞：无。M295 从全局能力图开始，不从单个数据集或页面缺陷继续拆分。

### M292-A～E：Planner 组件事实交接与可恢复澄清（已完成）

- 结果：完成组件 requirements/handoff、单组件 continuation、补充事实后的 context → re-plan → TaskPlan gate，以及 HTTP/async/artifact/view/Console 的脱敏投影。
- 验证：Docker M292 compact **3/3**、相邻 Planner/TaskPlan **19/19**、compileall、architecture strict、Node projection smoke、readiness 200。
- 下一步：M293-A 多组件 handoff 聚合与全局 continuation。

## 最近任务记录

### M291-A～E：Planner 语义完整性与能力计划闭合（已完成）

- 结果：新增 plan completeness/catalog consistency；Planner、TaskPlan bridge、跨入口 evidence 和 Console projection 已接通；组件事实不足统一为可恢复澄清。
- 验证：Docker Python **46/46**、新增状态映射回归 **6/6**、Node smoke、compileall、architecture strict、readiness 200；一次显式 live 安全澄清且无 execution run。
- 下一步：M292-B 组件级 requirements 与 preview 事实交接。

### M291-A～C：Planner 语义完整性与能力目录闭合（已完成）

- 结果：新增 `agent/runtime_core/plan_completeness.py`；目录投影输出 `catalog_consistency` 与 capability binding；Planner/TaskPlan bridge 拒绝语义不完整或不可物化的 success，并保留 `plan_completeness` evidence。
- 验证：Docker M291 + M290/M282/M279/M289/M286/M287 **46/46**，compileall、architecture strict、readiness 200 通过。
- 下一步：M291-D 跨入口语义恢复、artifact 和前端用户投影。

### M290-A～E：Provider Deadline 与真实 Composite 完成（已完成）

- 结果：统一 provider/harness deadline receipt 和预算边界；Composite component preview 按 Domain 隔离 session，复用匹配的 Domain workflow；空组件 success 在 TaskPlan 前被拒绝。
- 验证：Docker M290/M282/M279/M289/M286/M287 **41/41**，compileall、architecture strict、readiness 已作为阶段收口门禁保留；live 结果为安全失败且未创建 run。
- 下一步：M291-B Planner outcome 与 plan completeness gate。

### M289-B/C/D/E：真实 Composite Planner 纵向收口与阶段交付（已完成）

- 结果：planning matrix、prepared plan 跨入口执行 seam、前端 structured-output 摘要和 timeout safe receipt 已完成；M290 全局规划已创建。
- 验证：Docker M289/M280/M283 **15/15**、compileall、architecture strict、readiness 200、Node projection smoke 通过；真实 Composite probe 45 秒安全超时，未创建 run。
- 下一步：M290-A deadline/timeout 状态建模。

### M289-B/C/D：真实 Composite Planner 纵向收口（已完成）

- 结果：planning matrix、prepared canonical plan sync/async 对照、执行 run 创建门控、前端 structured-output 摘要已完成；真实 Composite timeout 保持安全失败。
- 验证：Docker M289/M280/M283 **15/15**、compileall、architecture strict、readiness 200、Node projection smoke 通过。
- 下一步：M289-E 文档、版本交付和 M290 全局规划。

### M289-B：Planner-to-TaskPlan 纵向 harness 与跨状态 evidence（已完成）

- 结果：新增 bounded planning outcome matrix、prepared canonical plan 的 sync/async acceptance seam，并将 planning probe 标记为 v2、显式记录 execution run 是否创建。
- 验证：Docker M289 + M280 **8/8**、compileall 通过；真实 Composite probe 45 秒 timeout，安全返回且未创建 run。
- 下一步：M289-C 对照真实/回放 canonical plan 的 sync、async、artifact、restart 与 Result/View/Evidence。

### M288-B/C/D/E：provider structured-output 能力协商与阶段交付（已完成）

- 结果：profile、wire adapter、Composite planning evidence、async/artifact/restart、live receipt 和前端 projection 已接通；阶段文档、中文问题记录、milestone、恢复账本和 M289 全局规划已同步。
- 验证：Docker M288/M279/M286/M287 **25/25**；compileall、architecture strict、生产 readiness/home 200、Node projection smoke、一次 live provider probe 通过。
- 下一步：M289-A 全局规划已创建，开始真实 Composite 成功/澄清/拒绝矩阵阶段。

### M288-B/C/D：provider structured-output 能力协商与跨入口 evidence（已完成）

- 结果：新增 provider-neutral profile 与 strict/object/unavailable mode；接入 OpenAI-compatible client、Composite planning evidence、async/artifact/restart safe projection、live receipt 和前端 projection。
- 验证：Docker M288/M279/M286/M287 **25/25**；compileall、architecture strict、生产 readiness/home 200、Node projection smoke 通过；显式 live provider probe `READY`，Chat Completions + `json_schema`，1 次请求 0 重试。
- 下一步：M288-E 文档、中文问题记录、版本交付和全局重规划。

### M281-E：动态 Composite 结果体验与跨入口一致性（已完成）

- 结果：新增 `spatial-agent.composite-view.v1`、FastAPI/stdlib `/view` 和前端 `projectionToPanels()`；M281/M278/M279 Docker **19/19**、compileall、architecture strict、JS/browser smoke 通过。
- 版本：`a2b240c` 已推送到 `origin/main`。
- 归档：M281 Spec/Plan、能力图、milestones、中文问题日志和工作快照已同步；任务账本已压缩为当前阶段。

### M282-A：全局能力图、Spec、Plan（已完成）

- 目标：把 Domain RequestFacts、能力发现、数据就绪和 Composite Planner 接成开放式请求公共入口，不增加领域专用流程。
- 改动：创建 `docs/m282-open-query-resolution-capability-map.md`、`docs/m282-open-query-resolution-spec.md`、`docs/m282-open-query-resolution-plan.md`；更新 `tasks/plan.md`、`tasks/todo.md`。
- 验证：能力模块依赖为 `request-context → capability-matching → planner-gateway → open-query-acceptance`，明确 v2 context、边界和 Docker 验收命令。

### M282-B：Context contract 与 RequestFacts 聚合（已完成）

- 目标：新增 `spatial-agent.composite-request-context.v2` 的有界 builder，复用 Domain Pack 的 `extract_request_facts()`/`discover()`/catalog，并生成稳定 context fingerprint。
- 改动：新增 `agent/composite_request_context.py`，接入 `CompositePlanningApplication`，增加事实/发现失败降级、能力 allowlist、context evidence fingerprint、预算和敏感字段过滤；新增 M282 定向契约测试。
- 验证：Docker M282/M279/M281 **20/20**；真实生产 Rule/本地上下文探测进入 v2 context 并按缺失事实澄清；compileall、architecture strict 通过。
- 阻塞：无。

### M282-C：Capability matching、缺失事实与结构化澄清（已完成）

- 结果：候选能力缺失字段只依据已选/唯一候选投影；发现失败、全部候选不可用、未知能力和上下文超限均结构化 fail closed；HTTP semantic command 保留同一 context clarification。
- 文件：`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`tests/test_m282_open_query_resolution.py`。
- 验证：Docker M282/M279/M281 **21/21**；compileall、architecture strict 和恢复脚本最小读取验证通过。
- 阻塞：无。

### M282-D：Planner gateway 与跨入口一致性（已完成）

- 结果：Rule/LLM Planner 接受同一 v2 context 并共享 canonical plan/allowlist；HTTP semantic command 保留 context、clarification 和 evidence 指纹；未知 context schema 在 provider 调用前拒绝。
- 文件：`agent/composite_planner.py`、`agent/application/composite_planning.py`、`tests/test_m282_open_query_resolution.py`。
- 验证：Docker M282 定向 **9/9**，M278 生命周期/HTTP **7/7**；联合回归 16/16，compileall、architecture strict 通过。
- 阻塞：无。

### M282-E：阶段验收、文档与版本交付（已完成）

- 结果：完成 Docker HTTP/readiness、阶段文档、中文问题记录、提交推送和全局重规划；真实模型短探测安全拒绝非法 Planner 输出，未创建 run。
- 验证：Docker M282/M279/M281 **24/24**、M278 **7/7**；compileall、architecture strict、恢复脚本最小读取、生产 `/health/ready` HTTP 200 通过。
- 版本：`a7e933b` 已提交并推送到 `origin/main`。
- 阻塞：无。

### M283-B：Planner gateway 收口（已完成）

- 结果：新增 `ReplayCompositePlanner`，与 Rule/LLM 复用同一 provider normalization、context schema 校验、canonical plan 和 capability allowlist；支持脱敏 alias replay，不保存模型原文。
- 文件：`agent/composite_planner.py`、`tests/test_m283_open_query_agent.py`。
- 验证：Docker M283/M282/M279 **23/23**；documented alias、未知字段、replay failure 和 v2 context parity 通过。
- 阻塞：无。

### M283-C：开放式成功切片与跨入口恢复（已完成）

- 结果：`CompositePlanningApplication` 通过可选 planning-evidence seam 进入同步/异步 Composite lifecycle；有界 planner evidence 可恢复到 result、evidence、artifact 和 SQLite/restart，不把完整 v2 context 写入执行请求。
- 文件：`agent/application/composite_runs.py`、`agent/application/composite_planning.py`、`tests/test_m283_open_query_agent.py`。
- 验证：Docker M283/M278/M282 **23/23**；HTTP semantic Replay submission、async artifact/restart evidence、M278 lifecycle/HTTP、M282 回归通过；compileall、architecture strict 通过。
- 阻塞：无。

### M283-D：动态结果体验与阶段里程碑（已完成）

- 结果：前端新增无领域分支的 `ConsoleResultProjection`，结论区展示阶段状态、关键发现、限制和下一步；详细执行信息继续渐进展开。
- 文件：`agent/web_assets.py`、`web/src/console_result_projection.js`、`web/src/console_app.js`、`web/src/index.html`、`web/src/styles.css`、`scripts/console_result_projection_smoke.js`、`scripts/console_result_projection_browser_smoke.js`。
- 验证：Node、Docker Node、静态资源、readiness、浏览器 projection smoke 通过；地图 smoke 暴露独立旧复位问题。
- 阻塞：无。

### M283-E：真实与跨入口验收（已完成）

- 结果：Docker 重建后 M283 **7/7**、compileall、architecture strict、生产 readiness/resource 200、Node/Docker/browser projection smoke 和 1 条真实 LLM + local GIS case 通过。
- Live receipt：`live-gis-spatial-overview` 为 `COMPLETED`，1 次请求、0 重试；只记录脱敏状态/耗时/token 摘要。
- 阻塞：地图 smoke 的清空对话后空间上下文复位问题已记录为后续独立任务。

### M283-F：文档、版本交付与全局重规划（已完成）

- 目标：同步阶段历史、恢复指针和全局下一阶段规划，完成提交推送。
- 待读/待修改：`scripts/resume_context.ps1`、`docs/m283-open-query-agent-plan.md`、`docs/milestones.md`、`docs/agent-context-resume.md`、`tasks/todo.md`、`tasks/task-progress.md`、`tasks/task-state.md`、`docs/agent-work-state.md`。
- 验证：复用 M283-E 已完成的精简证据；diff check、提交和推送均通过。
- 版本：`4d022f4` 已推送到 `origin/main`。
- 下一步：新的阶段先做七维度全局 Spec/Plan；当前没有进行中的代码任务。

### M284-A：会话清空与空间上下文一致性规划（已完成）

- 目标：建立 reset boundary、stale-render guard 和跨入口 browser regression 的公共契约。
- 待读/待修改：`docs/m284-session-reset-consistency-capability-map.md`、`docs/m284-session-reset-consistency-spec.md`、`docs/m284-session-reset-consistency-plan.md`、`tasks/todo.md`、`tasks/task-state.md`、`docs/agent-work-state.md`。
- 文件：`docs/m284-session-reset-consistency-capability-map.md`、`docs/m284-session-reset-consistency-spec.md`、`docs/m284-session-reset-consistency-plan.md`。
- 验证：规划边界与 M283 已知地图 smoke 失败证据一致；未修改运行时代码。
- 阻塞：无。

### M284-B/C：reset boundary 与 stale-render guard（已完成）

- 目标：公共 Registry/adapter reset 和 clear/session/domain generation 保持一致。
- 改动：Registry 增加有界 reset context 与 generation 失效；GIS adapter 清理地图实例、surface、selection 和按钮；Console 清空、切换会话/领域统一触发 reset，旧异步 render 返回 `superseded`。
- 文件：`web/src/console_renderer_registry.js`、`web/src/console_gis_plugin.js`、`web/src/console_app.js`、`scripts/console_reset_contract_smoke.js`。
- 验证：Node reset contract、plugin renderer regression、前端语法检查、Docker compileall 和 architecture strict 通过。
- 阻塞：无。

### M284-D：精简 reset 与地图浏览器回归（已完成）

- 目标：用最小浏览器契约覆盖地图选择、清空即时状态和延迟状态。
- 改动：地图 smoke 等待 bootstrap/domain readiness，并先建立空白会话边界，避免初始化历史恢复异步回写覆盖 fixture。
- 文件：`scripts/console_map_smoke.js`。
- 验证：串行 browser map smoke、M283 projection browser smoke 通过；Leaflet 图层/选择和清空后的即时、延迟空态均通过。
- 阻塞：无。

### M284-E：文档、版本交付与全局重规划（进行中）

- 目标：收口中文日志、里程碑、恢复快照与任务清单，提交并推送版本，再做全局重规划。
- 待读/待修改：`docs/agent-development-issues.md`、`docs/milestones.md`、`tasks/task-progress.md`、`tasks/task-state.md`、`tasks/todo.md`、`docs/agent-work-state.md`。
- 验证：M284 精简契约、Docker、readiness、browser 和 diff check 已通过；文档同步已完成，待 commit/push。
- 阻塞：无。

### M285-A：开放式 Planner 多工具编排全局规划（已完成）

- 目标：补齐开放式请求到 canonical TaskPlan/DAG 的系统级成功切片。
- 文件：`docs/m285-open-query-planner-capability-map.md`、`docs/m285-open-query-planner-spec.md`、`docs/m285-open-query-planner-plan.md`、`tasks/plan.md`、任务状态与工作快照。
- 验证：七维度全局盘点完成；明确 Rule/Replay/LLM parity、至少两步 replay、跨入口证据一致和显式 live 验收。
- 阻塞：无。

### M285-C/D：TaskPlan bridge 与跨入口证据（已完成）

- 目标：把开放式候选桥接到 canonical TaskPlan/DAG，并让安全 plan 投影沿 HTTP、async、artifact 和 restart 保持一致。
- 文件：`agent/runtime_core/composite_taskplan.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_planner.py`、M285/M283 定向测试。
- 验证：Docker M285/M283 **13/13**、compileall、architecture strict、readiness 通过；两步依赖 replay、非法工具拒绝、HTTP→async 和 artifact/restart evidence 通过。
- 阻塞：无。

### M285-E：live/交付收口与全局重规划（已完成）

- 目标：记录真实模型 Composite 输出问题，完成文档与版本交付，并规划下一阶段模型适配。
- 待读/待修改：`docs/agent-development-issues.md`、`docs/milestones.md`、`tasks/plan.md`、`tasks/todo.md`、`tasks/task-progress.md`、`docs/agent-work-state.md`。
- 验证：四次单请求 live probe 均安全拒绝，未创建 run；错误码为 `plan_response_field_invalid`、`plan_components_unexpected`、`taskplan_policy_unavailable`、`capability_not_registered`。已修复 `tools` capability projection 丢失和 Planner 非成功组件提示。
- 阻塞：中转模型输出未稳定遵守 Composite Planner schema；保持 fail closed。

### M286-A：中转模型 Planner 适配全局规划（已完成）

- 结果：完成七维度能力图、Spec、Plan；阶段覆盖 context identity、provider 有界兼容、失败分类、跨入口 projection、精简回放和单次 live 验收。
- 文件：`docs/m286-provider-planner-adaptation-capability-map.md`、`docs/m286-provider-planner-adaptation-spec.md`、`docs/m286-provider-planner-adaptation-plan.md`、`tasks/plan.md`、`tasks/todo.md`。
- 验证：规划边界与 M285 四类 live 失败证据一致；未运行重复业务测试。
- 阻塞：无。

### M286-B/C/D：context、provider 边界与选择 evidence（已完成）

- 结果：能力候选投影增加精确 `domain_id`、`capability_id`、`selection_key`、工具和结果类型摘要；LLM 提示要求复制注册身份；Composite live 输出预算正确传入懒加载生产 Planner；超预算组件计划拒绝而不截断；planner selection evidence 保存有界选择键。
- 文件：`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`agent/composite_planner.py`、`scripts/live_provider_probe.py`、`tests/test_m286_provider_planner_adaptation.py`。
- 验证：Docker M286 紧凑 contract **4/4**；未改变 Runtime、ToolRegistry 或执行权限边界。
- 阻塞：无；真实中转非法输出继续由 M286-E 的显式 live 记录。

### M286-E：阶段收口、显式 live 与版本交付（已完成）

- 结果：完成 M286 文档、问题记录、联合 Docker 门禁和显式 live；context identity、输出预算、evidence 选择键和超预算拒绝已交付。
- 验证：M286/M285/M283 联合 **17/17**、compileall、architecture strict、readiness 200；一条 live 在 context 层澄清，一条到达 provider 后 `plan_component_field_invalid`，均无 run。
- 下一阶段：M287 有界 Planner repair request/lineage，最多一次修复且复用同一 TaskPlan 门控。

### M287-A：有界 Planner 修复全局规划（已完成）

- 结果：完成七维度能力图、Spec、Plan；明确 repair 只处理 schema 结构错误，不改变事实、权限、能力或工具。
- 文件：`docs/m287-bounded-planner-repair-capability-map.md`、`docs/m287-bounded-planner-repair-spec.md`、`docs/m287-bounded-planner-repair-plan.md`。
- 验证：规划与 M286 的 provider schema 失败证据一致；未运行重复业务测试。
- 阻塞：无。

### M287-E：阶段收口、显式 live 与版本交付（已完成）

- 结果：完成 Repair Request/Lineage、一次性 provider repair、跨入口 evidence sanitizer、前端通用摘要和中文记录。
- 验证：M287/M286/M285/M283 联合 **23/23**、compileall、architecture strict、readiness 200、Node projection smoke 通过；真实 repair probe 仅调用一次修复，最终安全拒绝且无 run。
- 下一阶段：M288 provider wire-level structured-output 能力协商，不扩大 repair 次数。

### M288-A：Wire-level Structured Output 全局规划（已完成）

- 结果：完成七维度能力图、Spec、Plan；明确 provider profile 只影响 wire 参数，canonical schema/allowlist/TaskPlan 仍是最终门控。
- 文件：`docs/m288-wire-structured-output-capability-map.md`、`docs/m288-wire-structured-output-spec.md`、`docs/m288-wire-structured-output-plan.md`。
- 验证：规划与 M287 live repair 失败证据一致；未运行重复业务测试。
- 阻塞：无。

## 更新协议

1. 开始、完成或暂停子任务时更新状态、目标、文件、验证、阻塞和下一步。
2. 阶段收口时把完整结论归档到 Spec/Plan 或 milestones；本文件只保留当前阶段和最近记录。
3. 恢复上下文只读取本文件、当前阶段规划，以及当前任务明确列出的源码/测试文件。
