# Agent 任务进度账本

> 这是上下文恢复用的短账本，不是完整历史。每个子任务开始、完成或暂停时追加/更新一条记录；只保留可恢复所需的目标、状态、文件、验证、阻塞和下一步。详细阶段结论放在对应 Spec/Plan、milestones 和中文问题日志中。

## 使用规则

- 新对话或上下文压缩后，恢复脚本只读取本账本最近记录，不全文加载历史。
- 进行中的任务必须列出“需要修改的文件”；完成后保留实际改动文件和验证结果。
- `tasks/task-state.md` 保留为兼容性的详细当前状态；两者冲突时，以本账本的最新记录为恢复指针，并在完成子任务时同步修正详细状态。
- 状态只使用：`进行中`、`已完成`、`已暂停`、`受阻`。
- 不记录 API key、prompt、模型原文、私有路径、完整原始数据或敏感异常。

## 当前进行中

- 当前无进行中的代码子任务。
- M283 已完成并推送；下一阶段开始前先按七个全局维度编写新的 Spec/Plan，不在本阶段继续追加局部修补。

## 最近完成

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
