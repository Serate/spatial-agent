# 当前任务状态账本

> 上下文恢复时只读取本账本的当前阶段和最近记录。历史阶段结论在对应 Spec/Plan、milestones 和中文问题日志中；不要把本文件重新扩展成完整历史。

## 当前阶段

- 阶段：M285 开放式 Planner 多工具编排纵向切片
- 阶段规划：
  - `docs/m285-open-query-planner-capability-map.md`
  - `docs/m285-open-query-planner-spec.md`
  - `docs/m285-open-query-planner-plan.md`
- 执行方式：串行；默认测试离线精简；真实模型、GIS、Docker 和浏览器只做显式验收

## 最近任务记录

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

### M285-E：live/交付收口与全局重规划（进行中）

- 目标：记录真实模型 Composite 输出问题，完成文档与版本交付，并规划下一阶段模型适配。
- 待读/待修改：`docs/agent-development-issues.md`、`docs/milestones.md`、`tasks/plan.md`、`tasks/todo.md`、`tasks/task-progress.md`、`docs/agent-work-state.md`。
- 验证：两次单请求 live probe 均安全拒绝，未创建 run；错误码为 `plan_response_field_invalid`、`plan_components_unexpected`。
- 阻塞：中转模型输出未稳定遵守 Composite Planner schema；保持 fail closed。

## 更新协议

1. 开始、完成或暂停子任务时更新状态、目标、文件、验证、阻塞和下一步。
2. 阶段收口时把完整结论归档到 Spec/Plan 或 milestones；本文件只保留当前阶段和最近记录。
3. 恢复上下文只读取本文件、当前阶段规划，以及当前任务明确列出的源码/测试文件。
