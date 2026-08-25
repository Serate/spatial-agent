# 当前任务状态账本

> 上下文恢复时只读取本账本的当前阶段和最近记录。历史阶段结论在对应 Spec/Plan、milestones 和中文问题日志中；不要把本文件重新扩展成完整历史。

## 当前阶段

- 阶段：M282 开放式请求解析与受控 Composite Planner
- 阶段规划：
  - `docs/m282-open-query-resolution-capability-map.md`
  - `docs/m282-open-query-resolution-spec.md`
  - `docs/m282-open-query-resolution-plan.md`
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

### M283-D：动态结果体验与阶段里程碑（进行中）

- 目标：让前端动态消费 context、plan、clarification、answer、view 和 evidence，突出用户结论与下一步，不暴露思维链。
- 待读/待修改：`web/src` 对应 renderer/projection 文件、前端 contract/smoke 文件、`docs/m283-open-query-agent-plan.md`。
- 验证：先按需读取前端相关文件；使用精简 Node/browser smoke，Docker 显式验证，不调用网络。
- 阻塞：无。

## 更新协议

1. 开始、完成或暂停子任务时更新状态、目标、文件、验证、阻塞和下一步。
2. 阶段收口时把完整结论归档到 Spec/Plan 或 milestones；本文件只保留当前阶段和最近记录。
3. 恢复上下文只读取本文件、当前阶段规划，以及当前任务明确列出的源码/测试文件。
