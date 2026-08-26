# 当前任务状态账本

> 上下文恢复时只读取本账本的当前阶段和最近记录。历史阶段结论在对应 Spec/Plan、milestones 和中文问题日志中；不要把本文件重新扩展成完整历史。

> Goal 执行节奏补充：阶段按更完整的能力切片编排，尽量合并契约、实现、集成、文档和交付准备；开发中减少重复测试，阶段收口集中执行精简且有代表性的门禁。

## 当前阶段

- 阶段：M308 开放式 3+ 组件纵向链路与用户答案质量（已规划，A 进行中）
- 阶段规划：
  - `docs/m308-open-composition-vertical-slice-capability-map.md`
  - `docs/m308-open-composition-vertical-slice-spec.md`
  - `docs/m308-open-composition-vertical-slice-plan.md`
- 执行方式：串行；阶段任务包完整；默认测试离线精简并集中收口；真实模型、GIS、Docker 和浏览器只做显式验收

### M308-A：全局基线与 3+ 组件契约（进行中）

- 目标：以 M306 的真实 2 组件闭环为基线，冻结 3+ 组件混合 profile、答案事实不变和跨入口 evidence 契约。
- 当前文件：`docs/m308-open-composition-vertical-slice-capability-map.md`、`docs/m308-open-composition-vertical-slice-spec.md`、`docs/m308-open-composition-vertical-slice-plan.md`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`agent/application/composite.py`、`agent/application/composite_runs.py`、`agent/answer_generation.py`、`agent/composite_view.py`。
- 验证：开发期间只做必要静态/契约检查；A～D 合并后在 Docker 集中收口；本阶段真实模型最多一次且不重复 M306 live。
- 阻塞：无；不得绕过 canonical DAG、TaskPlan、ToolRegistry、workflow 或 execution binding。

### M306-F：文档、版本与全局重规划（已完成）

- 结果：M306 阶段门禁、真实 GIS/Economic 多组件同步/异步、artifact/restart 和唯一一次真实模型验收均通过；下一阶段已从全局架构缺口重规划为 M307。
- 验证：M306/M303/M281 **20/20**、compileall、architecture strict、Node projection、Service smoke、生产 acceptance、readiness **200** 和真实 restart 通过。

### M306-E：Docker 阶段验收（已完成）

- 目标：在 Docker 中集中验证多组件规划、执行、Result/Evidence/View、artifact、restart 和服务 readiness 的一致性，不重复真实模型请求。
- 当前文件：`docs/m306-open-composition-capability-map.md`、`docs/m306-open-composition-spec.md`、`docs/m306-open-composition-plan.md`、`tests/test_m306_composition_contract.py`、`tests/test_m303_open_composite_execution.py`、`tests/test_m281_dynamic_composite.py`、`scripts/m289_real_composite_acceptance.py`、`scripts/m280_real_composite_acceptance.py`、`scripts/architecture_check.py`。
- 验证：Docker M306/M303/M281 **20/20**、compileall、architecture strict、Node projection smoke、Service smoke、生产 acceptance 和 readiness **200** 通过；唯一一次真实模型 + 本地 GIS 验收形成 2 组件合法计划并完成 sync/async/artifact 对照。
- 阻塞：无；不得绕过 canonical DAG、TaskPlan、ToolRegistry 或 execution binding。

### M306-D：多类型 Result/Evidence 组合与用户投影（已完成）

- 结果：多组件结果按 Data Profile 聚合，View 由 Registry 驱动，答案生成器消费组合事实并在模型不可用时安全 fallback；前端只消费结构化 projection。
- 文件：复用 `agent/composite_contract.py`、`agent/composite_view.py`、`agent/answer_generation.py`、`web/src/console_result_projection.js` 及既有 M281/M302 契约，未增加领域专用分支。
- 验证：既有 M281/M302 组合与答案契约覆盖多类型、部分完成、动态 View 和答案 fallback；不重复运行相同回归。
- 阻塞：无。下一步进入 M306-E。

### M306-B：请求事实到能力候选与组件澄清（已完成）

- 结果：候选携带候选级缺失事实，discovery 区分 `facts_missing`，澄清可定位到 `domain_id/capability_id/field`；Planner Envelope 透传安全的缺口摘要，未改变执行授权。
- 文件：`agent/composite_request_context.py`、`agent/runtime_core/analysis_discovery.py`、`agent/runtime_core/planner_envelope.py`、`tests/test_m306_composition_contract.py`。
- 验证：Docker 新镜像 M306-A/B 精简契约 **6/6** 通过；未重复阶段级全量门禁。
- 阻塞：无。下一步进入 M306-C。

### M306-A：全局能力缺口、组件图和 typed input 契约冻结（已完成）

- 结果：冻结开放组件图、依赖先行、公共结果路径和 data-kind typed input 边界；非布尔 `required`、缺失/后置依赖、内部结果路径均 fail closed。
- 文件：`agent/runtime_core/composition.py`、`agent/composite_contract.py`、`agent/composite_planner.py`、`tests/test_m306_composition_contract.py`。
- 验证：补充 6 条精简契约；开发期仅完成静态边界检查，阶段门禁统一在 M306-E 执行。
- 阻塞：无。下一步进入 M306-B。

### M297-A：目录与类型边界冻结（待开始）

- 目标：盘点现有 capability/workflow/ToolRegistry/Result Registry，冻结开放式组合所需的公共 requirements、输入/输出 data profile、result_ref 和 `composition_invalid` 边界。
- 规划：`docs/m297-general-analysis-composition-capability-map.md`、`docs/m297-general-analysis-composition-spec.md`、`docs/m297-general-analysis-composition-plan.md`。
- 文件：当前先读取上述三个规划文件、`agent/runtime_core/plan_completeness.py`、`agent/runtime_core/execution_binding.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/analysis_discovery.py`、`agent/tools.py`；后续按账本增量加入 Domain catalog 和测试文件。
- 验证：开发期间只做静态/契约边界检查；M297-B～E 合并后集中运行精简门禁。
- 阻塞：无。不得绕过 execution binding，不得把未登记能力或 unknown readiness 当作可执行。

### M296-A～F：通用能力可执行闭合与真实跨域成功链路（已完成）

- 结果：execution readiness、跨 GIS/Economic TaskPlan/binding、真实 Docker 同步/异步/恢复链路和通用 Console 执行链路投影已闭合。
- 验证：M296 **9/9**、M295+M294 **9/9**、Docker compileall、architecture strict、Node projection smoke、生产 readiness HTTP 200；镜像已重建并重新创建。
- 交付：阶段 Spec/Plan、中文问题日志、milestone、恢复快照和任务清单已同步；版本 `6f8f2a2` 已提交，待推送后进入 M297。

### M295-A～F：全局开放式分析与数据发现闭环（已完成，待版本交付）

- 目标：在 M294 execution binding 之上，建立领域中立 discovery receipt，让开放式请求先完成能力/数据需求发现，再进入澄清或 validated TaskPlan。
- 规划：`docs/m295-global-open-analysis-discovery-capability-map.md`、`docs/m295-global-open-analysis-discovery-spec.md`、`docs/m295-global-open-analysis-discovery-plan.md`。
- 文件：`agent/runtime_core/analysis_discovery.py`、`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`evaluation/live_provider_probe.py`、`web/src/console_result_projection.js`、`web/src/styles.css`、`scripts/console_result_projection_smoke.js`、`tests/test_m295_open_analysis_discovery.py`。
- 验证：Docker M295 compact **5/5**；M295 + M281 + M285 + M291 + M293 + M294 合并回归 **30/30**；Docker compileall、architecture strict、Node projection smoke、生产 readiness **HTTP 200**、真实 Docker HTTP `NEEDS_CLARIFICATION`/discovery receipt 和真实模型单次安全澄清均通过或按结构化失败收口。
- 阻塞：无。不得新增区域、指标或固定问句分支；不得绕过 execution binding。
- 交付：待提交并推送 M295 版本；推送后基于七维度全局盘点进入 M296。

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

### M297：通用分析组合与跨类型结果闭合 — 已完成

- 结果：Result profile、组件输入引用、跨类型 data kinds、Composite View 和 execution binding 已通过公共 Runtime seam 闭合；GIS 与 Economic 仍由各自 Domain Pack 提供能力，未增加专题 Runtime 分支。
- 文件：`agent/runtime_core/composition.py`、`agent/composite_contract.py`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_request_context.py`、`agent/composite_view.py`、`agent/runtime_core/{composite_taskplan,execution_binding,plan_completeness,analysis_discovery}.py`、`scripts/m289_real_composite_acceptance.py`、M297 tests。
- 验证：Docker 相关精简契约 **55/55**；compileall、architecture strict、Node projection smoke、生产 readiness HTTP 200 通过。显式 live 到达 provider 并返回结构化澄清，当前 GIS readiness 未就绪，因此未宣称 live 跨域执行成功。
- 阻塞：无。安全澄清和数据未就绪均按既有生命周期返回，不放宽 schema、权限或执行 binding。

### M298：默认 Agent 模式与阶段可见性 — 已完成

- 结果：产品边界缺省使用 `openai + local`；`HTTPApplication` 仅在 FastAPI/stdlib 产品入口显式注入，低层应用保留 `rule + memory` 离线 fallback；Composite 组件继承顶层选择；前端默认呈现五个 Agent 阶段。
- 文件：`agent/runtime_defaults.py`、`agent/application/http.py`、`production_api.py`、`serve_api.py`、`run_demo.py`、`agent/composite_contract.py`、`web/src/{index.html,console_app.js,styles.css}`、M298 tests、配置/README/API 文档。
- 验证：默认配置、环境 allowlist、离线隔离、Composite 继承和前端契约通过；Docker M298 及相邻回归 **55/55**，compileall、architecture strict、Node projection smoke、readiness HTTP 200 通过。一次显式 live 在 context 预算修正后到达 provider，structured output 成功但模型返回澄清，未创建 run。
- 问题记录：已将 context 预算不一致、产品默认污染低层测试和 discovery 状态误判写入 `docs/agent-development-issues.md`。
- 下一步：M299-A 以全局视角设计默认 Agent 的最小上下文与成功/澄清/不可用验收矩阵。

### M299-A/B：Planner envelope 与统一预算 — 已完成

- 结果：新增 `spatial-agent.planner-envelope.v1`；真实模型只接收请求事实、候选能力、选择摘要和候选执行契约四层投影，完整 Context 仍供 Runtime 校验/恢复使用。
- 文件：`agent/runtime_core/planner_envelope.py`、`agent/composite_request_context.py`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`agent/runtime_core/analysis_discovery.py`、M299 contract。
- 验证：M299/M297/M298 **18/18**；受影响的 M282/M286/M287 **19/19**；Docker compileall、architecture strict、Node projection smoke、readiness HTTP 200 通过。
- 修复：M287 测试替身补齐当前 execution binding 要求的已校验 TaskPlan 和 policy，未放宽生产门禁。
- 阻塞：无。下一步进入 M299-C，补统一选择/澄清 evidence。

### M299-C：选择与澄清 evidence — 已完成

- 结果：新增 `spatial-agent.selection-evidence.v1`，把候选能力身份、data profile、readiness、workflow IDs、选择状态、澄清信息和 next actions 统一投影；前端按标签展示，不暴露内部 ID。
- 文件：`agent/runtime_core/selection_evidence.py`、`agent/application/composite_planning.py`、`web/src/console_result_projection.js`、M299 tests。
- 验证：Docker 精简契约 **26/26**，Node projection smoke、compileall、architecture strict、readiness 200 通过。
- 阻塞：无。下一步完成 M299-D 的阶段状态与旧载荷降级。

### M299-D：阶段状态与跨入口 evidence 投影 — 进行中

- 结果：阶段条消费完整响应对象，等待确认、澄清和默认 Agent 阶段可见；`selection-evidence.v1` 已贯通 planning attach、同步/异步安全持久化和 Composite View，前端只展示用户标签与下一步动作。
- 额外修复：Economic Domain 的自然问法区域提取清理通用查询前缀和“地区生产总值”中的指标噪声，不增加区域专用分支。
- 文件：`agent/runtime_core/selection_evidence.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`domains/economic/planner.py`、`web/src/console_{app,result_projection}.js`、M299/M263 tests。
- 验证：待 Docker 重建后集中运行 M299、M263、Node projection、compileall、architecture strict、readiness 与真实经济数据 smoke。
- 追加：显式 live provider 探测在 45 秒 deadline 内 timeout，按 provider failure 记录；真实 Replay/Rule local 数据链路已可执行，且同步响应 View 已与异步/恢复统一。
- 阻塞：无。

## 更新协议

1. 开始、完成或暂停子任务时更新状态、目标、文件、验证、阻塞和下一步。
2. 阶段收口时把完整结论归档到 Spec/Plan 或 milestones；本文件只保留当前阶段和最近记录。
3. 恢复上下文只读取本文件、当前阶段规划，以及当前任务明确列出的源码/测试文件。

### M301：Planner-first 开放问题解析 — 已完成

- 结果：无关 Domain 的缺失事实不再在 Planner 前阻断；新增领域中立 readiness 投影，保留 selected-component fact handoff、TaskPlan、ToolRegistry、workflow 和 execution binding 的严格门禁。
- 结果：内部 Context/目录/discovery 与 provider Planner Envelope 分层预算；内部默认 256 KiB，模型 Envelope 默认 96 KiB；重复一致性明细压缩为摘要。
- 验证：Docker M301/M300/M295/M294/M278 **25/25**，compileall、architecture strict、readiness HTTP 200 通过；显式 live 为 provider timeout，未创建 execution run。
- 当前阶段：M302 分阶段 Planner 上下文与开放问题成功链路，规划与恢复入口见 `docs/agent-work-state.md` 和 `tasks/task-progress.md`。

### M299-D/E/F：阶段收口与全局重规划 — 已完成

- 结果：产品入口实测默认 `openai + local`；Agent 阶段、selection evidence、同步/异步 View 和 artifact/restart 恢复已闭合。
- 修复：Composite 异步导出先发布 artifact，再写入最终完成快照，避免轮询看到无 artifact 引用的 `COMPLETED` 中间状态。
- 验证：Docker M299/M263 **19/19**；Node projection smoke、compileall、architecture strict 和 readiness 200 通过；真实 Economic local 与 Replay/Rule 对照通过；中转 live timeout 按 provider failure 记录且未创建 run。
- 文档：M299 问题、milestone、进度账本和恢复快照已同步；M300 capability map、Spec、Plan 已创建。
- 当前阶段：M299 已完成，版本 `f3bfbeb` 已提交推送；下一阶段为 M300-A 全局成功率/状态矩阵审查。

### M302-A/B：阶段化 Planner 上下文投影 — 已完成

- 结果：公共 `spatial-agent.planner-envelope.v1` 现在声明有限的 `projection_stage`：`discovery`、`selection`、`execution`、`repair`。Runtime Context Builder 保存 discovery 摘要；LLM provider 初次规划和一次结构修复分别重投影为 selection/repair；execution/repair 已选能力存在时仅保留对应组件、workflow、readiness、result profile 和事实缺口。
- 结果：已有 Envelope 通过安全白名单直接规范化，避免重新投影时丢失 workflow/result closure；planning evidence 区分 Context projection stage 与 provider projection stage。
- 文件：`agent/runtime_core/planner_envelope.py`、`agent/composite_request_context.py`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`tests/test_m302_stage_aware_planner_context.py`、`tasks/task-progress.md`。
- 验证：Docker M302 与相邻 M299/M300/M301/M286/M287 **34/34**，compileall、architecture strict、Service smoke 和 readiness HTTP 200 通过；未执行真实 provider 请求。
- 阻塞：无。下一步进入 M302-C，验证 selected-component handoff 与 TaskPlan/binding identity 的阶段化投影。

### M302-C：选中组件到执行投影的 identity 闭合 — 已完成

- 结果：execution-stage projection 只在 TaskPlan/DAG、plan completeness 和 execution binding 全部通过后生成；execution binding 纳入 capability identity，plan fingerprint 对新 binding 覆盖 capability，projection 校验组件集合、顺序、领域、能力、依赖和 required identity。
- 结果：`execution_identity` 纳入 Planner Envelope 安全规范化；planner evidence 只保留阶段、请求/绑定指纹、组件 ID、候选数和 byte size，不复制完整 plan、工具参数或私有 binding。
- 文件：`agent/runtime_core/planner_envelope.py`、`agent/runtime_core/execution_binding.py`、`agent/application/composite_planning.py`、`tests/test_m302_stage_aware_planner_context.py`。
- 验证：Docker 新镜像 M302-C + M294 + M293 + M292 **19/19**；compileall、architecture strict、Service smoke、生产 `/health/ready` **200** 全部通过。
- 阻塞：无。未执行真实 provider 请求，未读取或保存密钥、模型原文、私有路径或真实原始数据。
- 当前阶段：进入 M302-D，优先从全局结果链路检查 Result → answer/evidence → View/Console 的事实一致性和用户可读性。

### M302-D/E：结果投影事实闭合与阶段交付 — 已完成
- 目标：让 Result、answer/evidence、View 和 workspace 共享同一结构化事实来源，并完成 Docker、HTTP、异步、artifact、恢复和显式 live 收口。
- 实际修改：`agent/composite_view.py`、`result_contract.py`、`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`、`tests/test_m302_stage_aware_planner_context.py`；同步中文问题日志、M302 Plan、milestone 和恢复账本。
- 修复：Registry 的 ViewSpec 现在同时登记到 workspace，避免 fallback View 面板与 workspace 声明漂移；计数字段和 answer-generation evidence 继续走公共安全投影。
- 验证：Docker M302/答案/Composite **26/26**；生产 HTTP/异步/artifact/restart **ok**；compileall、architecture strict、Service smoke、Node projection smoke、readiness **200**。
- 显式 live：中转结构化输出可达，1 请求、0 重试、约 47 秒后安全返回 `NEEDS_CLARIFICATION`，未创建 run；未保存密钥、prompt、模型原文或私有数据。
- 阻塞：无。下一步：全局重规划 M303，验证 LLM Planner 对已就绪 GIS/Economic 能力的合法多组件 DAG 选择与真实执行。

### M303-A：全局能力图、Spec、Plan 与状态矩阵 — 已完成
- 目标：从全局七维度提升开放式 LLM Composite 的真实成功率，让模型选择已就绪能力并进入合法多步执行，不复制 Runtime 或领域专用流程。
- 已完成：创建 `docs/m303-open-composite-execution-capability-map.md`、`docs/m303-open-composite-execution-spec.md` 和 `docs/m303-open-composite-execution-plan.md`；冻结 planner decision、canonical plan、执行闭合、跨入口和 live 交付模块及依赖顺序。
- 当前任务：M303-B 审查并实现结构化模型选择到 canonical Composite 请求/DAG 的安全适配；只读取 M303 规划文件、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`agent/runtime_core/planner_envelope.py` 和新增精简测试文件。
- 阻塞：无。

### M303-B：结构化模型输出到 canonical DAG 适配 — 已完成

- 结果：Planner 先生成 canonical Composite request，再从可信 canonical 组件重建 projection，解决大小写、依赖和输入引用 identity 漂移；严格拒绝非字符串依赖、非布尔 `required`、未知字段和 LLM 携带 workflow。
- 文件：`agent/composite_planner.py`、`tests/test_m303_open_composite_execution.py`。
- 验证：Docker 新镜像 M303-B 与 M279/M280/M283/M287 相邻回归 **32/32**；真实 `CompositeTaskPlanBridge` 的闭合预验收 **6/6**；未调用真实 provider。
- 阻塞：无。下一步进入 M303-C，扩展共享 TaskPlan/DAG、ToolRegistry policy、binding 与拒绝矩阵验收。

### M303-C：Replay/Rule/LLM 共享执行闭合 — 进行中

- 目标：合法多组件计划必须经过同一 TaskPlan/DAG、workflow、ToolRegistry 和 execution binding；非法能力、事实、依赖和 workflow 在创建 run 前终止。
- 当前文件：`agent/application/composite_planning.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`、`tests/test_m303_open_composite_execution.py`。
- 验证：开发期间只做必要检查，阶段收口集中使用 Docker 精简回归、跨入口验收和架构门禁。
- 阻塞：无。

### M303-C：Replay/Rule/LLM 共享执行闭合 — 已完成

- 结果：Rule、Replay、LLM 通过同一 canonical request、组件 identity、DAG 依赖、TaskPlan bridge 和 execution binding；LLM 不得提供 workflow/task plan，未知能力、环依赖、空计划和非法字段均在创建 run 前拒绝。
- 文件：`agent/composite_planner.py`、`tests/test_m303_open_composite_execution.py`。
- 验证：Docker M303-C 精简契约 **7/7**；合法双组件使用真实 `CompositeTaskPlanBridge` 和 `build_execution_binding()`，未调用真实 provider。
- 阻塞：无。下一步进入 M303-D，使用真实 Docker GIS/Economic 数据做跨入口执行与恢复对照。

### M303-D：真实数据跨入口执行与恢复对照 — 进行中

- 目标：同一合法 canonical 计划完成 sync、async、artifact、SQLite/restart 和 evidence identity 对照。
- 当前文件：`scripts/m289_real_composite_acceptance.py`、`scripts/m280_real_composite_acceptance.py`、`production_api.py`、`agent/application/composite_runs.py`。
- 当前诊断：真实后台 worker 和 Domain service 已返回完成；`CompositeRunApplication.get_run()` 在持久化的初始 `PLANNING` 快照没有嵌套 Composite result 时构造失败 fallback，造成轮询误判并过早结束。
- 修复边界：active Composite snapshot 必须投影为 `PLANNING`/`EXECUTING` 与 pending Composite result；验收脚本改用 async observability 作为终态信号。
- 验证：待补最小回归后在 Docker 重跑真实数据 acceptance；provider 仅在计划与数据 readiness 通过后显式调用一次。
- 阻塞：无；已获得稳定最小复现。

### M303-D/E/F：真实跨域验收、阶段门禁与交付 — 已完成

- 结果：活动 Composite 快照改为正确投影 `PLANNING`/`EXECUTING`；真实 Docker GIS/Economic sync/async、artifact、SQLite/restart 和 evidence 对照通过，`recovery_count=1`。
- 验证：M303 与相邻 Composite 回归 **12/12**；compileall、architecture strict、Node projection、Service smoke、生产 HTTP 和 readiness **200** 通过。
- 显式 live：1 次、60 秒、0 重试，`FAILED/timeout`、`error_plane=harness`、未创建 run；不保存模型原文、密钥或私有数据。
- 交付：中文问题日志、milestone、M303 Plan、任务账本、恢复快照已同步；M304 capability map、Spec、Plan 已创建。

### M304-A～F：Provider-backed 规划可靠性与可恢复交互 — 已完成
- 结果：新增 provider health/deadline/runtime evidence 公共 seam；LLM 适配器保留有界 provider 错误码和 retryable；Composite View、HTTP/异步结果与 Console 对 provider failure 使用统一结构化投影。
- 验证：重建 Docker 后 M304/M300/M303 精简回归 **24/24**；compileall、architecture strict、Node projection、Service smoke、生产 acceptance 和 readiness **200** 通过。
- 显式 live：1 次、60 秒、0 重试，`FAILED/timeout`、`error_plane=harness`、`execution_run_created=false`；未保存密钥、prompt、模型原文或私有数据。
- 下一阶段：M305 Provider-backed 成功率与可恢复交互优化；规划文件为 `docs/m305-provider-success-capability-map.md`、`docs/m305-provider-success-spec.md`、`docs/m305-provider-success-plan.md`。

### M305-A～E：Provider-backed 成功率与可恢复交互 — 已完成
- 结果：冻结状态/动作矩阵，新增 planner attempt 与 canonical plan receipt，统一 Envelope 预算、repair lineage 和跨入口 evidence；只有 accepted TaskPlan bridge 与 validated execution binding 才标记 `executable`。
- 验证：Docker M304/M305 **14/14**、M303/M283 **16/16**，合并 **30/30**；compileall、architecture strict、Service smoke、生产 acceptance、Node projection 和 readiness **200** 通过。
- 显式 live：1 次、60 秒、0 重试；真实 provider 返回合法单组件计划并完成 sync/async/artifact 对照，未保存密钥、prompt 或模型原文。
- 下一步：完成 M305-F 文档、版本交付和全局重规划。
