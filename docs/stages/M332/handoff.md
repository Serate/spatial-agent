# M332 阶段交接

## 状态

- 阶段：`M332` 真实模型复杂任务有界执行与增量反馈
- 状态：M332-F 已完成，阶段验收通过，待提交并进入全局重规划
- 基线：M331 交付版本 `11d7492`
- 协作：单 Agent，最大并发度 1；测试与 GIS 优先使用 Docker

## 当前目标

解决复杂真实模型请求在规划阶段长时间无反馈的问题：为 Planner、ReAct、工具执行、答案生成和整个 Run 建立独立预算；在阻塞期间发送真实心跳；超时后提供结构化恢复；异步终态不能被迟到 worker 覆盖。

## 必要文件

- `docs/stages/M332/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/runtime_core/run_budget.py`
- `agent/runtime_core/progress.py`
- `agent/integration/structured_response.py`
- `agent/llm_planner.py`
- `agent/answer_generation.py`
- `agent/runtime.py`
- `agent/runtime_core/run_lifecycle.py`
- `agent/run_events.py`
- `agent/application/async_runs.py`
- `agent/application/service_state.py`
- `agent/persistence/sqlite_store.py`
- `production_api.py`
- `web/src/console_run_events.js`
- `web/src/console_app.js`
- M332 直接相关紧凑测试

## 恢复规则

只读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本 handoff 和当前 Plan 子任务列出的源码/测试。完整历史、全量源码、全量测试、Prompt、模型原文、网页正文和敏感配置按需读取。

## 当前交接

- M332-0：已完成阶段能力地图、Spec、Plan 与本交接文件；已切换热状态。
- M332-A：已完成 `RunBudget` 深模块，统一总预算、阶段预算、单次 provider 预算和安全 receipt。
- M332-B：已完成 `ProgressCoordinator` 与兼容 RunEvent 扩展，支持有序阶段事件、heartbeat、重试和恢复提示。
- M332-C：已完成 Provider、Planner、ReAct、普通答案与 Composite 答案的调用级 timeout/deadline/安全进度回调；Provider 重试退避受 deadline 限制，结构化响应仍先完整校验。
- 验证：M331 结构化响应 + M332 预算、进度、Provider 紧凑测试 `17/17` 通过；只使用 fake client，未保存模型原文或敏感配置。
- M332-D/E：Runtime 生命周期、reaper、SQLite/内存/Artifact 终态 fence 已接入；极短超时、兼容 factory、SQLite 超时和事件序号竞争均有回归覆盖。
- M332-F：Docker 定向回归 `15/15`、compileall、architecture strict、服务 smoke、readiness `200` 和 Console 规划等待/答案流/事件/结果投影 smoke 通过。
- 真实验收：使用 `docker compose --env-file .env.production -f docker-compose.prod.yml ...` 挂载 `D:/dataset/agent`，显式 `gis` + `openai` 复杂请求 `COMPLETED`；模型 evidence 为 `live_model/success`，SSE 共 `812` 个事件，断点续传后 `811` 个事件，异步/轮询/Artifact/evidence 对照通过。
- M332-F 修复：ReAct 后续 Planner 超时不再覆盖先前成功的 `planner_metrics`；新增紧凑回归，保证公开 model evidence 不会因最后一次失败而误报。
- 交付状态：M332 代码和文档已准备提交；不保存模型原文、Prompt、网页正文、工具源码、密钥或隐藏思维链。

## 全局重规划输入

- 产品：保持“问一句、持续看到真实进展、得到通俗答案”的体验；下一阶段优先答案质量和开放问题成功率。
- Runtime：预算、阶段事件、恢复和终态 fence 已形成公共边界；除跨入口差异外不继续增加专用分支。
- Planner：继续验证开放 ReAct 的多领域能力发现、组合、有限恢复和超时降级，不以单次 live 成功替代稳定性验收。
- Domain/数据：保持数据目录、readiness、来源证据和可替换 Domain Pack；扩展真实数据能力时不把区域或问句硬编码进 Runtime。
- 部署/测试：生产 Docker 启动固定使用 `--env-file .env.production`，并在 live 验收前检查宿主机卷和容器 `/data`；默认测试保持离线、精简、按风险分层。

## 验收与风险

- 需要覆盖阻塞 provider、阶段 timeout、reaper 与迟到 worker、SSE 续传和前端 heartbeat projection。
- 不强杀任意 Python 线程；provider socket timeout 与沙箱进程 timeout 是硬边界。
- 不保存任何真实模型原文、Prompt、密钥或隐藏思维链。
