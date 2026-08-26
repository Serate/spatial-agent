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
- Goal 级上下文约束：恢复或继续任务时，只读取当前任务明确必需的文件；仅判断状态时只读取工作快照和任务账本尾部，不批量读取历史文档、全量源码、全量测试或模型响应。发现新的直接依赖后，才将其加入必要文件清单。

## 当前进行中

### M300 阶段收口 — 进行中

- 目标：从开放问题事实理解、能力发现、受控计划、provider 可靠性和答案体验形成完整 Agent 成功切片，不增加专题硬编码。
- 已完成：M300-A～C 的 Domain Request Understanding 投影、能力就绪门禁、默认结构化答案启用和 provider 失败状态修正。
- 需要读取/修改：`docs/m300-open-agent-success-spec.md`、`docs/m300-open-agent-success-plan.md`、`agent/application/composite_planning.py`、`tests/test_m300_open_agent_success.py`、`tasks/task-progress.md`、`docs/agent-development-issues.md`。
- 验证节奏：阶段收口集中运行 M300 与相邻生命周期契约、compileall、architecture strict、Node projection 和 readiness；真实 provider 只做显式单次验收。
- 阻塞：无。provider 不稳定时保持 fail closed，不保存模型原文或敏感配置。
- 下一步：完成文档/版本交付后，从全局七维度重规划下一阶段。

### M294-A～E：已验证计划到执行/答案/证据闭合 — 已完成

- 目标：建立领域中立 `spatial-agent.execution-binding.v1`，让 validated TaskPlan/DAG 成为 Composite coordinator 的唯一受校验执行输入，并让同步、异步、artifact、SQLite/restart、View、Evidence 和答案引用同一 binding identity。
- 实际修改：`agent/runtime_core/execution_binding.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/run_lifecycle.py`、`agent/runtime.py`、`agent/service.py`、`agent/application/submission.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/application/composite.py`、`agent/composite_contract.py`、`agent/composite_view.py`、`agent/contract_versions.py`、`production_api.py`、`serve_api.py`、`tests/test_m294_execution_binding_closure.py`。
- 结果：完整 TaskPlan 仅在内部 binding 中传递，公开/Artifact/View 只保留安全结构投影；执行前校验 request/组件/计划/DAG/工具/结果类型和 binding fingerprint；Domain Runtime 直接消费 validated plan，不再重新猜测步骤；可选结构化 Composite 答案生成失败时回退到可读答案。
- 验证：Docker M294 compact、M293/M291/M285/M281 合并回归 **25/25**；Docker 真实 GIS Service `get_raster_metadata` binding 验收通过；compileall、architecture strict、生产 `/health/ready` **200** 通过。
- 阻塞：无。生产 Composite coordinator 缺少 binding 时 fail closed；旧注入式 coordinator 仅保留显式兼容入口。
- 下一步：基于项目全局七维度规划 M295，优先闭合通用数据发现/能力匹配和开放式跨领域分析入口，不增加单区域专用分支。

### M288-B/C/D/E：provider structured-output 能力协商与阶段交付 — 已完成

- 目标：建立 provider-neutral structured-output profile，接入 OpenAI-compatible Responses/Chat Completions wire mode，并让 Composite planning、持久化、live receipt 和前端 projection 保留同一份脱敏能力证据。
- 实际修改：`agent/provider_structured_output.py`、`agent/openai_config.py`、`agent/llm_planner.py`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`evaluation/live_provider_probe.py`、`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`、`tests/test_m288_wire_structured_output.py`。
- 结果：默认 strict `json_schema`；显式 `json_object` 仅改变 wire 请求，不放宽本地 schema/allowlist/TaskPlan 门控；`unavailable` 在 transport 前 fail closed；provider 来源、reason、status、error、attempts/retries 均有界且不含密钥。
- 验证：Docker M288 + M279 + M286 + M287 **25/25**；Docker compileall、architecture strict、生产 readiness 200、首页 200、Node projection smoke 通过；一次显式 live provider probe 为 `READY`、Chat Completions、`json_schema`、schema enforced、1 次请求 0 重试。
- 阻塞：无。真实 Composite 多组件输出仍按 M285/M287 证据保持严格门控，不能将 provider connectivity probe 误记为跨域执行成功。
- 下一步：完成 M288-E 文档/问题记录/提交推送，然后从全局七维度规划 M289 真实 Composite 成功/澄清/拒绝矩阵。

## 最近完成

### M293-A～E：多组件事实协调与可恢复 Composite 续跑 — 已完成

- 结果：新增 composite fact handoff 与 grouped continuation；多个组件缺失事实只返回一个 token，补充后按 component_id/Domain 合并并重新走 context、Planner、TaskPlan/DAG gate；HTTP、safe evidence、View 和 Console 支持组件集合 identity。
- 文件：`agent/runtime_core/clarification_continuation.py`、`agent/runtime_core/component_fact_handoff.py`、`agent/runtime_core/composite_taskplan.py`、`agent/application/composite_planning.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`、`tests/test_m293_multi_component_continuation.py`。
- 验证：Docker 合并回归 **26/26**、Node projection smoke、compileall、architecture strict、生产 readiness **200**；未重复 live provider。
- 阻塞：无。组件集合漂移、未知组件/字段和未完成澄清均 fail closed；M292 单组件 continuation 保持兼容。
- 下一阶段：M294 已验证计划到执行/答案/证据闭合。

### M292-A～E：Planner 组件事实交接与可恢复澄清 — 已完成

- 结果：新增 `component-fact-handoff.v1` 与有界 continuation；Planner 选择的组件可声明 requirements、已知事实、workflow 约束和字段级澄清；补充事实后重新构建 context、重新规划并通过 TaskPlan/completeness gate。
- 跨入口：HTTP `composite_plan`、同步/异步提交、planning evidence、artifact/async safe projection、Composite View 和 Console 均保留脱敏 continuation identity；前端展示组件缺失字段，不展示 token。
- 兼容：为旧 M285/M283 replay fixture 补齐最小 canonical workflow，恢复 M291 严格 TaskPlan gate 下的既有回归语义。
- 文件：`agent/runtime_core/component_fact_handoff.py`、`agent/runtime_core/clarification_continuation.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/preview.py`、`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`agent/application/http.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`web/src/console_result_projection.js`、`tests/test_m292_component_fact_handoff.py`。
- 验证：Docker compact **3/3**、相邻回归 **19/19**、compileall、architecture strict、Node projection smoke、生产 `/health/ready` **200**；未执行重复 live 请求。
- 阻塞：无。单组件 continuation 已完成，多组件统一 handoff 是 M293 范围。
- 下一阶段：M293 多组件事实协调与可恢复 Composite 续跑。

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

### M292-B：组件级 requirements 与 preview 事实交接 — 进行中
- 目标：建立 `spatial-agent.component-fact-handoff.v1`，把已选组件的公共 requirements、已知事实、工作流约束和缺失字段安全交给 Domain preview。
- 待读/待修改：`agent/runtime_core/component_fact_handoff.py`、`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/preview.py`、`agent/application/submission.py`、`agent/service.py`、`agent/runtime.py`、`domains/gis/domain.py`、`domains/economic/domain.py`。
- 验证：开发期间只做语法/静态检查；M292-B～D 合并后集中运行精简 continuation contract、compileall、architecture 和 readiness 门禁。
- 阻塞：无。
- 下一步：实现 handoff contract 与 preview 入口透传；缺失事实时返回组件级、字段级澄清，不创建 execution run。

### M295-A：全局基线与 discovery receipt 契约冻结 — 已完成
- 目标：在 M294 execution binding 之上，为开放式请求建立领域中立、版本化、可恢复的能力/数据发现投影。
- 需要修改/实际修改：已完成 M295 capability map、Spec、Plan 的七维度盘点；冻结 `spatial-agent.analysis-discovery.v1`、`needs_facts`、`data_unavailable`、`capability_unavailable`、`discovery_invalid` reason code 与安全/预算边界。
- 验证：完成现有 RequestFacts、Capability Catalog、Domain discovery/readiness、continuation 和 execution binding 的边界核对；实现期间只做必要静态检查，阶段收口统一执行精简门禁。
- 阻塞：无。
- 下一步：实现 M295-B Discovery Gateway，并把 receipt 接入 Composite Request Context。

### M295-B：领域中立 Discovery Gateway — 进行中
- 目标：把 Domain Pack 已提供的 facts、候选能力、workflow 和 readiness 聚合为唯一 bounded discovery receipt；不选择工具、不创建计划、不绕过 execution binding。
- 需要修改/实际修改：`agent/runtime_core/analysis_discovery.py`、`agent/composite_request_context.py`、`tests/test_m295_open_analysis_discovery.py`。
- 验证：开发期间仅执行语法/静态检查；完成 M295-B～D 后集中执行 compact contract、相邻回归、Docker compileall、architecture strict 和 readiness。
- 阻塞：无。
- 下一步：先实现 receipt 校验、fingerprint、候选/数据需求/readiness 聚合和敏感字段过滤，再接入 context 的 clarification 与 planner 投影。

### M295-B～D：Discovery Gateway、Planner 门禁与结果投影 — 已完成
- 目标：将 Domain facts、候选能力、workflow 和 readiness 聚合为唯一 `spatial-agent.analysis-discovery.v1`，并贯通 Planner、生命周期、View、Evidence、Artifact 和前端。
- 需要修改/实际修改：新增 `agent/runtime_core/analysis_discovery.py`；`CompositeRequestContextBuilder` 接入 receipt 和统一 request/discovery fingerprint；Planner 校验不可执行候选；planning evidence、Composite View、async/artifact safe projection 和 Console 动态显示 discovery 状态；补充 workflow 声明字段回退与中文标签。
- 验证：M295 compact **5/5**；M295 + M281 + M285 + M291 + M293 + M294 合并回归 **30/30**；Node projection smoke、Docker compileall、architecture strict 通过。
- 阻塞：无。
- 下一步：完成 M295-E/F 的真实 Docker/HTTP/live 证据整理、中文问题记录、提交推送和全局重规划。

### M295-E：跨领域真实数据与显式验收 — 已完成
- 目标：验证真实生产 Docker/HTTP 和真实模型在开放式跨领域请求上的 discovery、澄清和安全降级，不保存模型原文或敏感配置。
- 需要修改/实际修改：`evaluation/live_provider_probe.py` 增加 discovery 摘要的安全报告投影；生产容器重建并使用 `gis + economic` 请求验收。
- 验证：Docker 生产 HTTP 返回 `spatial-agent.analysis-discovery.v1`、稳定 request/discovery fingerprint、`NEEDS_CLARIFICATION`、`needs_facts/request_facts_missing`，缺少经济指标时给出“经济指标”中文标签；未创建 execution run。真实模型单次 structured-output 请求安全返回 `NEEDS_CLARIFICATION`，0 组件、0 重试、未创建 run；readiness HTTP 200。
- 阻塞：真实中转模型尚未形成稳定合法的多组件执行计划；本阶段按设计保留安全澄清，不放宽 schema 或权限。
- 下一步：将真实模型“可达但需澄清/不稳定”作为 M296 纵向成功链路的输入约束。

### M295-F：中文记录、版本交付与全局重规划 — 进行中
- 目标：同步问题日志、阶段里程碑、恢复快照和任务清单，提交并推送 M295 版本，再按项目全局规划 M296。
- 需要修改/实际修改：`docs/agent-development-issues.md`、`docs/milestones.md`、`docs/agent-work-state.md`、`tasks/task-state.md`、`tasks/task-progress.md`、`tasks/plan.md`、`tasks/todo.md`。
- 验证：阶段代码和测试已完成；文档修改后执行 `git diff --check`，提交后核对 commit/push 和工作树状态。
- 阻塞：无。
- 下一步：写入 M295 问题记录和 M296 全局能力图/Spec/Plan，提交推送阶段版本。

### M295-F：中文记录、版本交付与全局重规划 — 已完成
- 目标：完成 M295 文档、问题记录、milestones、恢复快照和 M296 全局计划；阶段版本待提交推送。
- 需要修改/实际修改：`docs/agent-development-issues.md`、`docs/milestones.md`、`docs/agent-work-state.md`、`tasks/task-state.md`、`tasks/task-progress.md`、`tasks/plan.md`、`tasks/todo.md`；新增 M296 capability map、Spec、Plan。
- 验证：最终 Docker compileall、architecture strict、readiness 200 和 HTTP discovery/clarification 已通过；M295 compact 5/5、合并回归 30/30、Node smoke 已有阶段证据。
- 阻塞：无。
- 下一步：提交并推送 M295 版本，然后开始 M296-A。

### M296-A：全局基线与 execution-readiness 契约冻结 — 进行中
- 目标：在不新增第二套生命周期的前提下，冻结 capability → workflow → ToolRegistry → TaskPlan/result type 的执行就绪边界。
- 需要修改/实际修改：`docs/m296-executable-capability-closure-capability-map.md`、`docs/m296-executable-capability-closure-spec.md`、`docs/m296-executable-capability-closure-plan.md`、`agent/runtime_core/plan_completeness.py`、`agent/runtime_core/execution_binding.py`、`agent/runtime_core/composite_taskplan.py`、`agent/tools.py`。
- 验证：开发期间只做静态/契约边界检查；M296-B～E 合并后集中执行精简门禁。
- 阻塞：无。
- 下一步：在公共 Runtime 能力面生成受限 execution contract；由 plan completeness 统一校验 workflow 工具、工具 schema 和 Result Registry，并将 readiness 投影回 discovery/candidate，之后再进入 B～E 的连续纵向闭合。

### M296-A1：公共 execution contract 与 catalog readiness — 已完成
- 目标：让 discovery 的 `execution_ready` 由真实 ToolRegistry 与 Domain Result Registry 的结构化契约支持，区分 `workflow_unbound`、`schema_invalid` 和 `ready`；不执行工具、不新增生命周期。
- 需要修改/实际修改：`agent/runtime_core/plan_completeness.py`、`agent/runtime_core/capabilities.py`、`agent/runtime.py`、`agent/service.py`、`agent/application/composite_planning.py`、`agent/composite_request_context.py`、`agent/runtime_core/analysis_discovery.py`、`agent/runtime_core/composite_taskplan.py`、`tests/test_m296_execution_readiness.py`。
- 验证：Docker 重建成功；M296 readiness + M295 discovery **9/9**；真实 Docker Host catalog 验收显示 Economic 5 个、GIS 10 个能力结构 ready，未闭合能力明确为 `workflow_unbound`。
- 阻塞：无。
- 下一步：验证 `spatial_analysis` 与 Economic trend/compare 作为事实完整候选能物化 canonical TaskPlan，并进入统一 execution binding。

### M296-B：选定能力的 Workflow → TaskPlan → binding 物化 — 进行中
- 目标：用已有 `spatial_analysis` 与 Economic 工作流验证选定能力的连续闭合；不把未绑定能力伪装成可执行，不新增第二套生命周期。
- 需要修改/实际修改：`agent/runtime_core/plan_completeness.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`、`agent/application/composite_planning.py`、`tests/test_m296_execution_readiness.py`（按验证结果补充）。
- 验证：开发期间仅做真实 Host 的 planning/TaskPlan 静态闭合检查；阶段收口集中执行跨入口与 Docker 门禁。
- 阻塞：无。
- 下一步：构造不依赖固定问句的 Replay 组合候选，确认 GIS + Economic 的 TaskPlan、DAG、binding identity 一致。

### M296-B1：真实 Service 的能力到 Workflow 解析 — 进行中
- 目标：修复 Composite bridge 调用真实 `AgentService` 时无法把已选 capability 解析为 Domain workflow，避免把 ready handoff 误报为组件事实澄清。
- 需要修改/实际修改：`agent/service.py`、`agent/runtime.py`、`agent/runtime_core/capabilities.py`、`agent/runtime_core/composite_taskplan.py`、`domains/economic/domain.py`、`tests/test_m296_execution_readiness.py`。
- 验证：已在 Docker 真实 Host 重现 `taskplan_component_clarification`，handoff 为 `ready` 但 preview workflow 为空；先补充回归测试再修复。
- 阻塞：无。
- 下一步：补齐公共解析 seam 和 Economic capability/workflow 映射，再重跑跨域 Replay planning。

### M296-B2：Workflow index 透传与注册校验 — 进行中
- 目标：让 Composite request context 保留受限 workflow index，使 bridge 能验证 Domain resolver 返回的 template，而不是把已注册 workflow 误判为未注册。
- 需要修改/实际修改：`agent/composite_request_context.py`、`tests/test_m296_execution_readiness.py`。
- 验证：Docker Replay planning 已越过组件事实澄清，但当前重现 `taskplan_workflow_not_registered`；原因是 context 缺少 `workflow_index`。
- 阻塞：无。
- 下一步：透传安全 workflow index 后重新验证两组件的 TaskPlan、DAG 和 binding。

### M296-B3：候选工具 allowlist 完整透传 — 进行中
- 目标：修复 Composite context 对候选工具列表的过度截断，确保 capability、workflow 和 TaskPlan bridge 使用同一份有界 allowlist。
- 需要修改/实际修改：`agent/composite_request_context.py`、`tests/test_m296_execution_readiness.py`。
- 验证：已在 Docker 真实 Host 复现 GIS `spatial_analysis` 的第 9 个工具被 context 截掉；待修复后集中验证 9 工具回归及跨域 Replay planning。
- 阻塞：无。
- 下一步：运行精简 Docker 回归，确认 `taskplan_tool_not_allowlisted` 消失并继续验证 TaskPlan/DAG/binding。

### M296-B3：候选工具 allowlist 完整透传 — 已完成
- 目标：修复 Composite context 对候选工具列表的过度截断，确保 capability、workflow 和 TaskPlan bridge 使用同一份有界 allowlist。
- 需要修改/实际修改：`agent/composite_request_context.py`、`tests/test_m296_execution_readiness.py`。
- 验证：Docker 重建后 M296 定向 **9/9**；真实 Host 中 GIS `spatial_analysis` 的 9 个工具完整透传，`taskplan_tool_not_allowlisted` 消失。
- 阻塞：无。
- 下一步：进入阶段级跨域规划、执行、异步/恢复和前端投影收口。

### M296-B～D：跨域 Planner → TaskPlan → binding → Docker 执行闭合 — 已完成
- 目标：验证 GIS 与 Economic 通过同一公共闭合链路生成计划并执行，不新增领域专用 Runtime 流程。
- 需要修改/实际修改：复用 M296-B1/B2/B3 代码；未增加领域专用执行分支。
- 验证：Docker Replay 规划 `PLANNED`，GIS 9 步 + Economic 2 步均 `accepted`；真实 GIS/Economic 同步执行 `COMPLETED` 并生成 artifact；异步执行 `QUEUED → COMPLETED`，View、Evidence、SQLite/restart 的 binding fingerprint 一致；真实 LLM 单次规划和实际执行均 `COMPLETED`，2 个组件、0 重试、binding `validated`、artifact 可用。
- 阻塞：无。
- 下一步：完成通用 Console 的执行链路状态展示、阶段文档与集中门禁。

### M296-E：通用 Console 执行链路投影 — 进行中
- 目标：在不增加 GIS/Economic 页面分支的前提下，让前端从结构化 planning/evidence 识别已验证执行链路，并用用户可读状态展示。
- 需要修改/实际修改：`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`。
- 验证：待阶段收口运行 Node、Docker 资源和必要浏览器 smoke；不展示 binding fingerprint、工具名或模型原文。
- 阻塞：无。
- 下一步：完成前端 smoke 后更新阶段文档、快照和版本记录。

### M296-E：通用 Console 执行链路投影 — 已完成
- 目标：在不增加 GIS/Economic 页面分支的前提下，让前端从结构化 planning/evidence 识别已验证执行链路，并用用户可读状态展示。
- 需要修改/实际修改：`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js`；前端仅增加执行链路用户标签和有界 chip 容量。
- 验证：Node projection smoke 通过；Docker 镜像重建后生产资源可用，readiness HTTP 200；不展示 binding fingerprint、工具名、prompt 或模型原文。
- 阻塞：无。
- 下一步：完成 M296-F 阶段文档、提交推送和 M297 全局规划。

### M296-F：阶段收口、版本交付与全局重规划 — 已完成
- 目标：完成 M296 的集中门禁、中文问题记录、milestone、恢复快照和任务清单，并按七维度规划下一阶段。
- 需要修改/实际修改：`docs/agent-development-issues.md`、`docs/milestones.md`、`docs/agent-work-state.md`、`tasks/task-state.md`、`tasks/task-progress.md`、`tasks/plan.md`、`tasks/todo.md`；新增 M297 capability map、Spec、Plan。
- 验证：Docker M296 **9/9**；M295+M294 **9/9**；Docker compileall、architecture strict、Node projection smoke、生产 readiness HTTP 200；生产镜像已重建并重新创建。
- 阻塞：无。
- 下一步：推送版本 `6f8f2a2` 后开始 M297-A；继续复用现有 Runtime、Planner、ToolRegistry 和生命周期。

### M297-A：目录与类型边界冻结 — 进行中
- 目标：盘点现有 capability/workflow/ToolRegistry/Result Registry，冻结开放式组合所需的公共 requirements、输入/输出 data profile、result_ref 和 `composition_invalid` 边界。
- 规划：`docs/m297-general-analysis-composition-capability-map.md`、`docs/m297-general-analysis-composition-spec.md`、`docs/m297-general-analysis-composition-plan.md`。
- 验证：开发期间只做静态/契约边界检查；M297-B～E 合并后集中运行精简门禁。
- 阻塞：无。
- 下一步：将组件引用与 TaskPlan/binding 的最终语义继续收口，验证同步/异步/恢复投影不丢失来源 identity，再进入跨类型结果 View 与开放组合验收。

### M297-A～B：目录类型投影与组合引用校验 — 进行中
- 目标：让 Planner 看到 Result Registry 的输出 data profile，并为 Composite 组件建立有界、显式、可恢复的组件结果引用。
- 需要修改/实际修改：`agent/runtime_core/capabilities.py`、`agent/application/composite_planning.py`、`agent/composite_request_context.py`、`agent/composite_planner.py`、`agent/composite_contract.py`、`agent/runtime_core/composition.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`、`tests/test_m297_general_analysis_composition.py`。
- 验证：Docker 已重建；M297 新契约与 M296/M294 binding 回归 **18/18**、compileall、architecture strict 通过；实际 GIS + Economic Planner catalog 约 77 KiB，在 96 KiB 有界预算内，19 个 GIS 和 6 个 Economic Result profile 可投影。
- 阻塞：无。
- 下一步：将组件引用与 TaskPlan/binding 的最终语义继续收口，验证同步/异步/恢复投影不丢失来源 identity，再进入跨类型结果 View 与开放组合验收。

### M297-B1：结果投影保留组合依赖 — 已完成
- 目标：修复 Composite 结果投影遗漏 `depends_on` 导致合法的组件输入引用在结果契约归一化时被误判为非法。
- 需要修改/实际修改：`agent/composite_contract.py`；以 M297 组合契约测试覆盖结果投影与来源血缘。
- 验证：修复前 Docker 回归复现该问题；修复后 M297 + M296 + M294 **18/18**，compileall 和 architecture strict 通过。
- 阻塞：无。
- 下一步：进入 M297-C，验证已有注册能力的开放式组合规划与执行闭环。

### M297-C：少量工具的开放式组合闭环 — 进行中
- 目标：确认 Rule、Replay 和 LLM Planner 经过同一组合规范化、能力 allowlist、TaskPlan bridge 与 execution binding，能够表达两个以上已登记能力的开放请求。
- 需要修改/实际修改：优先复用现有 `agent/composite_planner.py`、`agent/runtime_core/composite_taskplan.py`、`agent/runtime_core/execution_binding.py`；仅在验证发现公共缺口时修改，不增加领域专用分支。
- 验证：Docker 代表性 Planner、TaskPlan/DAG 和 HTTP/恢复契约 **6/6**；Rule/Replay/LLM 共用规范化与执行绑定，默认测试保持离线。
- 阻塞：无。
- 下一步：进入 M297-D，核对跨类型 Result/View 的动态展示和未知类型降级。

### M297-C：少量工具的开放式组合闭环 — 已完成
- 目标：确认 Rule、Replay 和 LLM Planner 经过同一组合规范化、能力 allowlist、TaskPlan bridge 与 execution binding，能够表达两个以上已登记能力的开放请求。
- 实际修改：复用 M279～M296 的公共 Planner、TaskPlan 和 binding seam；同步修复 M280 测试替身以实现当前执行就绪接口，未增加领域专用分支。
- 验证：Docker 代表性用例 **6/6**；两步 DAG、HTTP 异步提交、planner evidence 和 SQLite/artifact/restart 证据通过。
- 阻塞：无。
- 下一步：完成 M297-D 的跨类型 Result/View 与用户答案投影。

### M297-D：跨类型 Result/View 与用户答案 — 进行中
- 目标：让 vector、raster、metrics、timeseries、document_evidence 和 composite 的类型、摘要、来源、限制与视图声明通过同一安全 projection 到 Console；未知类型必须可读降级。
- 需要修改/实际修改：按源码审计结果决定 `agent/composite_view.py`、`web/src/console_result_projection.js`、`scripts/console_result_projection_smoke.js` 及对应契约测试。
- 验证：开发期间只做必要静态检查；完成 D 后集中运行 Node projection 与 Docker contract。
- 阻塞：无。
- 下一步：先核对现有 Composite View 是否丢失 data profile/view kind/evidence，再补最小公共投影。

### M297-D：跨类型 Result/View 与用户答案 — 已完成
- 目标：让 vector、raster、metrics、timeseries、document_evidence 和 composite 的类型、摘要、来源、限制与视图声明通过同一安全 projection 到 Console；未知类型可读降级。
- 实际修改：`agent/composite_view.py` 增加整体/组件 `data_kinds`；`web/src/console_result_projection.js` 增加跨类型归一化与“结果组成”展示；Node smoke 增加混合类型场景。
- 验证：Node syntax/smoke 通过；Docker M297 contract **6/6**、compileall、architecture strict、生产 readiness HTTP **200** 通过。
- 阻塞：无。
- 下一步：进入 M297-E，执行真实数据、跨入口恢复和显式模型验收。

### M297-E：真实数据、恢复与显式模型验收 — 进行中
- 目标：在 Docker 中核对 GIS + Economic 跨类型组合的同步/异步/artifact/SQLite/restart/HTTP identity 与 evidence 一致性，并保留必要降级证据。
- 需要修改/实际修改：优先复用现有 `evaluation/` harness 与 M296 生产入口；只有真实验收暴露公共缺口时才修改 Runtime/Domain。
- 验证：先运行一次现有 harness 帮助/离线路径，再执行阶段集中真实验收；不保存模型原文、prompt、密钥或原始私有数据。
- 阻塞：无。
- 下一步：修正验收 harness 对 prepared execution binding 的透传，再运行最小代表性场景。

### M297-E1：验收 harness binding 透传 — 已完成
- 目标：让真实 Composite 验收复用 Planner 已验证的 execution binding，并比较同步/异步的 request、binding、结果类型和 data kinds identity。
- 实际修改：`scripts/m289_real_composite_acceptance.py`；prepared 对象的非序列化 binding 现在会传入 sync/async 两条执行入口。
- 验证：脚本具备安全 live 入口；真实 provider structured output 可达但返回结构化澄清，未创建 execution run；未知数据 readiness 不会被伪装成成功。
- 阻塞：无；真实 GIS 当前 readiness 未就绪，故不宣称本轮 live 跨域执行成功。

### M297-F：阶段收口、版本交付与全局重规划 — 已完成
- 目标：完成通用组合、跨类型结果、真实/恢复验收和阶段文档收口。
- 实际修改：`agent/runtime_core/composition.py`、Composite request/result/View、Planner context、execution binding、acceptance harness、M297 contract 和 Node projection；未增加领域专用 Runtime 分支。
- 验证：Docker 相关精简契约 **55/55**；compileall、architecture strict、Node projection smoke、生产 readiness HTTP 200 通过。真实模型请求已到达 provider，但安全返回澄清；未保存模型原文、密钥或私有数据。
- 下一步：交付 M297 版本后进入 M298 默认 Agent 模式与阶段可见性。

### M298-A～D：默认 Agent 配置、产品入口与阶段可见性 — 已完成
- 目标：把已有 Runtime 能力接到产品默认入口；缺省使用 `openai + local`，Composite 组件继承顶层选择，前端默认显示简洁 Agent 阶段。
- 实际修改：新增 `agent/runtime_defaults.py`；CLI、FastAPI 和 stdlib 产品入口显式启用产品默认；共享 `HTTPApplication` 保留离线 fallback；Composite 组件统一继承顶层选择；前端新增“发现能力 → 理解请求 → 生成计划 → 执行任务 → 汇总结果”阶段条。
- 规格与计划：`docs/m298-default-agent-mode-spec.md`、`docs/m298-default-agent-mode-plan.md`。
- 验证：默认配置/环境 allowlist、低层离线隔离、Composite 继承和前端静态契约均已覆盖；阶段条不展示 prompt、模型原文或思维链。
- 阻塞：无。

### M298-E：集中门禁、显式 live、文档与交付 — 已完成
- 目标：确认“产品默认真实 Agent”已经启动，同时保持测试和降级语义可控。
- 验证：Docker M298 及相邻回归 **55/55**；compileall、architecture strict、Node projection smoke、生产 readiness HTTP 200 通过；一次显式 live 请求在修正 context 预算后到达 provider，structured output 通道成功但模型返回澄清，未创建 run。
- 结论：产品默认模式已启动并可观测；真实模型的“可达”已验证，真实跨域成功仍受当前模型输出和 GIS readiness 约束，系统按设计安全澄清。
- 下一阶段：M299 聚焦默认 Agent 的最小上下文与可执行成功率，从全局能力、数据 readiness、用户体验、恢复和部署一致性重新规划，不回退到规则默认。

### M299-A：全局基线、验收矩阵与上下文预算 — 进行中
- 目标：从项目整体冻结默认 Agent 的 success、clarification、data unavailable、provider failure 四类状态，以及 Context Builder、LLM Planner、provider payload 和恢复边界的统一预算。
- 规格与计划：`docs/m299-default-agent-success-capability-map.md`、`docs/m299-default-agent-success-spec.md`、`docs/m299-default-agent-success-plan.md`。
- 当前结论：M298 live 已证明 provider structured-output 通道可达；默认 Agent 后续应优先压缩无关上下文、保留动态能力发现和执行身份，不能退回规则默认。
- 当前明确文件：`agent/composite_request_context.py`、`agent/composite_planner.py`、`agent/application/composite_planning.py`、`web/src/console_result_projection.js`、`tests/test_m299_default_agent_success_path.py`。
- 验证策略：M299-A 只做契约审计和 Spec/Plan；M299-E/F 合并执行一轮 Docker 精简门禁与显式验收。
- 阻塞：无。
- 下一步：测量当前多领域 context 的字段贡献，设计分层 Planner envelope，不修改领域专用代码。

### M299-A：全局基线、验收矩阵与上下文预算 — 已完成
- 目标：冻结 success、clarification、data unavailable、provider failure 四类状态，以及 Context Builder、Planner、provider payload 和恢复边界的统一预算。
- 实际修改：新增 `spatial-agent.planner-envelope.v1` 公共边界，预算统一为 96 KiB；保留脱敏、版本和 fail-closed 语义。
- 验证：M299 envelope 契约、私有字段过滤和 128 字节超限拒绝通过；未改变真实模型默认值或执行门禁。
- 阻塞：无。
- 下一步：完成分层 provider 投影并补选择/澄清 evidence。

### M299-B：分层 Planner context 与统一投影预算 — 已完成
- 目标：将 provider 输入分为请求事实、能力索引、选择摘要和执行契约，减少无关目录重复，同时保留可规划的 data profile 与 workflow 闭合信息。
- 实际修改：`agent/runtime_core/planner_envelope.py`；Context Builder 写入 envelope；LLM Planner 只发送 envelope；Planner evidence 记录 envelope 版本、层级、预算和候选数；候选 workflow 只按候选能力过滤。
- 验证：M299/M297/M298 **18/18**；M282/M286/M287 **19/19**（M287 旧测试替身同时补齐当前 TaskPlan/policy 契约）；Docker compileall、architecture strict、Node projection smoke、readiness HTTP 200 通过。
- 阻塞：无。
- 下一步：进入 M299-C，统一选择、澄清、不可用原因和下一步动作的可读 evidence。

### M299-C：选择与澄清 evidence — 已完成
- 目标：统一成功、澄清、不可用和失败结果的能力选择摘要，保留候选 identity、data profile、readiness、workflow 闭合和下一步动作。
- 实际修改：新增 `agent/runtime_core/selection_evidence.py`，由 Composite planning attach seam 写入 `planner_evidence.selection_evidence`；前端 projection 归一化并展示用户可读的能力选择提示。
- 验证：M299/M297/M298/M287 **26/26**；selection identity 与私有字段过滤通过，Node projection smoke 通过。
- 阻塞：无。
- 下一步：完成 M299-D，让阶段状态与澄清动作消费同一结构化 evidence，并验证旧载荷降级。

### M299-D：阶段状态与澄清动作投影 — 进行中
- 目标：让 Console 阶段条和澄清区区分 discovering、planning、executing、summarizing、不可用与等待补充，并将 next_actions 绑定到结构化澄清。
- 已完成：`console_result_projection.js` 已消费 `selection-evidence.v1`，展示能力选择和下一步提示，不展示内部 ID 或模型原文；阶段条支持等待确认状态；选择证据已接入 CompositeRunApplication 安全持久化和 Composite View。
- 当前文件：`agent/runtime_core/selection_evidence.py`、`agent/application/composite_runs.py`、`agent/composite_view.py`、`web/src/console_result_projection.js`、`web/src/console_app.js`、`scripts/console_result_projection_smoke.js`、`tests/test_m299_default_agent_success_path.py`。
- 验证：开发期间不重复运行全量测试；阶段收口统一运行 Node smoke 与 Docker contract。
- 阻塞：无。
- 额外修复：真实 Economic 链路发现自然问法的区域事实提取会污染查询参数，已在 `domains/economic/planner.py` 增加通用噪声清理并补充真实数据形状测试。
- 额外修复：同步 Composite 返回体直接附带与异步/恢复一致的 `spatial-agent.composite-view.v1`；显式 live 已记录为中转 provider timeout，未创建 execution run。
- 下一步：集中重建 Docker，运行 M299/M263 contract、真实 Replay/Rule 数据验收、旧载荷安全降级检查并收口阶段文档。

### M299-D：默认 Agent 黑盒核验 — 进行中
- 目标：确认用户可见产品入口是否真正启用默认 Agent，而不是仅保留底层能力。
- 核验：运行中的 `ai-agent-spatial-agent-1` healthy；`/health/ready` 返回 200；容器内产品默认选择为 `openai + local`。历史上 M298 之前产品默认长期为 `rule + memory`，因此“能力存在但默认未启动/未显形”的判断成立；当前产品入口已启用，不能把中转 provider timeout 误判为 Agent 未启动。
- 阶段回归：Docker 重建后 M299/M263 共 18 项中 17 项通过；唯一失败为 `test_selection_evidence_survives_sync_async_and_restart_views` 的 artifact 引用断言，尚未判定为生产代码缺陷。
- 当前诊断：最小失败点是测试场景拿不到 `artifact_ref`；待核对 `export_artifact` 输入和同步/异步/artifact 投影链路。
- 下一步：确认 artifact 引用是否因测试未开启导出而缺失；若生产链路确有丢失，再补公共投影并重跑单一回归。

### M299-D/E/F：阶段收口与全局重规划 — 已完成
- 结果：确认产品入口已默认启用 `openai + local`，前端默认展示 Agent 阶段；补充同步/异步/澄清/恢复的选择证据与即时 View。
- 额外修复：Composite 异步路径改为先写 artifact、再公开最终 `COMPLETED` 快照，避免完成状态与导出证据短暂不一致；新增阻塞 artifact store 回归。
- 验证：Docker M299/M263 **19/19**；Node projection smoke、compileall、architecture strict、生产 `/health/ready` **200**；真实 Economic local 数据与 Replay/Rule 恢复对照通过；显式中转 live 为 timeout，未创建 run，按 provider failure 记录。
- 交付文档：已更新 `docs/agent-development-issues.md`、`docs/milestones.md`、`docs/agent-work-state.md`、`tasks/task-state.md`、`tasks/plan.md`、`tasks/todo.md`；M300 capability map、Spec、Plan 已创建。
- 交付：版本 `f3bfbeb` 已提交并推送。
- 下一步：进入 M300-A，先审查全局能力图和成功率状态矩阵。

### M300-A：全局能力图、Spec、Plan 与状态矩阵 — 规划中
- 目标：从产品、架构、数据、模型、部署、体验和测试七个维度，提升开放问题的默认 Agent 成功路径，不新增专题硬编码。
- 已完成：创建 `docs/m300-open-agent-success-capability-map.md`、`docs/m300-open-agent-success-spec.md` 和 `docs/m300-open-agent-success-plan.md`；冻结五个能力模块及依赖顺序。
- 当前状态：开始实现开放问题的通用事实与能力选择边界；默认测试策略保持 Docker、精简、阶段收口集中验证。
- 本任务必要文件：`agent/request_model.py`、`agent/composite_request_context.py`、`agent/application/composite_planning.py`、`agent/composite_planner.py`、`domains/gis/request_model.py`、`domains/economic/planner.py`、`tests/test_m300_open_agent_success.py`。

### M300-A：Domain Request Understanding 投影 — 已完成
- 结果：Composite 请求上下文现在通过 Domain Pack 的 `request_understanding_guidance` seam 携带有界的事实字段、任务/约束/证据提示；Planner envelope 将其投影给 Rule/Replay/LLM，未实现该 seam 的 Domain 显式标记为不可用，不由 Runtime 添加词法分支。
- 文件：`agent/composite_request_context.py`、`agent/runtime_core/planner_envelope.py`、`tests/test_m300_open_agent_success.py`。
- 验证：Docker M300-A 精简契约 **4/4**；`git diff --check` 通过。未运行重复的全量回归。
- 阻塞：无。
- 下一步：进入 M300-B，核对开放问题的候选能力组合、执行就绪状态和 TaskPlan 闭合。

### M300-B/D：能力就绪门禁与默认答案体验 — 已完成
- 结果：Composite Planner 在规范化阶段拒绝显式未注册、无工作流或 `execution_ready=false` 的能力；Composite 运行层仅对带 LLM Planner evidence 的成功结果启用结构化答案生成，Rule/Replay/直接执行/未配置模型保持离线回退，并支持 `SPATIAL_AGENT_DISABLE_LLM_ANSWER=1`。
- 文件：`agent/composite_planner.py`、`agent/application/composite_runs.py`、`production_api.py`、`serve_api.py`、`docs/m300-open-agent-success-spec.md`、`docs/m300-open-agent-success-plan.md`、`docs/agent-development-issues.md`、`tests/test_m300_open_agent_success.py`。
- 验证：Docker M300 + M279 + M282 + M281 精简回归 **30/30**；其中新增 M300 契约 **6/6**。未运行 live provider。
- 阻塞：无。
- 下一步：完成 M300-C 的 provider 失败/有限修复状态闭合，再做 Docker 静态门禁、readiness 和显式真实数据验收。

### M300-C：provider 失败状态与可重试动作 — 已完成
- 结果：`planner_provider_failed` 不再伪装成事实澄清；规划响应返回 `FAILED`、有界 `failure.v1`（planning/provider/retryable）和“稍后重试”，未创建 execution run 的语义保持不变。
- 文件：`agent/application/composite_planning.py`、`tests/test_m300_open_agent_success.py`、`docs/m300-open-agent-success-spec.md`、`docs/m300-open-agent-success-plan.md`、`docs/agent-development-issues.md`。
- 验证：待阶段收口统一运行 M300 精简契约和相邻回归；开发期间只做必要 diff 检查。
- 阻塞：无。真实中转失败仍按 provider failure 记录，不通过增加重试或放宽校验制造成功。
- 验证：Docker M300/M278/M294 **15/15**；compileall、architecture strict、Node projection smoke、生产 readiness **200** 通过；真实模型两次显式验收分别为事实澄清和 provider failure，均未创建 execution run。
- 下一步：提交并推送 M300 阶段版本，再从项目全局重规划下一阶段。
