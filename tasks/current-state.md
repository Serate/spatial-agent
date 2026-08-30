# 当前任务状态

> 热状态文件，只保留当前阶段、进行中任务、必要文件和最近验证。

## 当前阶段

- 阶段：`M331`
- 当前任务：M331-F 阶段交付与全局重规划
- 状态：M330-A～F、M331-A～F 已完成，待提交阶段版本
- 基线：`0ce3ba4`
- 协作：单 Agent，最大并发度 1；测试、GIS 和 live 验收优先使用 Docker

## 已完成

- M328 受控开放行动闭环已完成并提交：ReAct、Web evidence、工具提案审批恢复、答案流、SSE、Artifact 和 Docker/live 验收。
- M329 capability map、Spec、Plan、handoff 已建立。
- M329-0 已完成热状态和恢复入口收敛。
- M329-A 已完成：`request-mode.v1` 已接入 Result、SQLite/artifact、execution record 和终态事件。
- M329-B 已完成：`GeneralCapabilityHost` 聚合四个已登记 Domain Pack，按 owner dispatch 和 preflight，局部 provider 失败降级，
  工具/实际结果类型冲突 fail-closed，并提供稳定上下文指纹。
- M329-C-1 已完成：`GeneralRuntimePack`/`GeneralResultRegistry`/`build_general_runtime` 已接入聚合 Host；规则模式可完成诚实
  direct-answer fallback，通用 Runtime 仍不携带 GIS 专用策略。
- M329-C-2 已完成：默认 full ReAct、白名单 Web 搜索和受控工具提案在 Docker 中通过真实模型验收；普通回答、经济工具链、
  Web 不可用降级和 proposal `WAITING_FOR_DECISION` 均保持统一生命周期与安全边界。
- M329-D 已完成：产品 HTTP/CLI 默认进入通用 Runtime；同步、preview、异步、事件和 Artifact 返回 `general` 身份，
  `/domains/{domain_id}` 继续使用显式 Domain Runtime。
- M329-E/F 已完成：SQLite/Artifact 重启、多轮会话、SSE `Last-Event-ID`、proposal 同一 Run 恢复、显式 Domain 隔离、
  Docker/真实模型/索引/前端阶段门禁全部通过；答案生成上下文不再把内部执行状态写成用户仍在等待。

## 已完成（当前阶段）

- M330-A：新增通用直接回答场景矩阵和紧凑契约测试；答案生成允许不依赖外部数据的通用请求直接回答，真实模型验收通过。
- M330-B：补充目录 workflow 到工具操作的结果类型推导；通用 Registry 优先使用已校验结果，未知或歧义结果仍 fail-closed；
  完成多域目录、schema/结果契约和真实模型能力选择验收。
- M330-C：完成 Web 状态、受控工具提案 sandbox/审批/同一 Run 恢复、Provider 局部降级、ReAct 预算/澄清/参数校验验收。
- M330-D：完成 Runtime 事件、SSE/Last-Event-ID、轮询、Artifact、前端 projection 和产品 readiness 验收。
- M330-E：完成阶段合并回归与真实模型纵向验收，未保存模型原文、Prompt、网页正文、工具源码或密钥。

## 已完成（上一阶段）

- M330：完成直接回答、能力发现、受控 Web/工具提案、降级恢复、实时事件、默认 HTTP/SSE/Artifact 与真实模型纵向验收。

## 进行中

- M331-F：已收口 M331 文档、索引和全局重规划；下一阶段优先处理真实模型复杂规划延迟与增量反馈。

## 必要文件

- `docs/stages/M331/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/context_engineering.py`
- `agent/runtime_state.py`
- `agent/sqlite_store.py`
- `agent/artifact_store.py`
- `agent/run_events.py`
- `agent/application/async_runs.py`
- `tests/` 中与上下文、事件回放和恢复直接相关的紧凑测试
- `tasks/current-state.md`
- `docs/document-index.json`

## 验证

- M328 Docker 紧凑回归、readiness、compileall、architecture/index、SSE/Artifact/live 基线已通过。
- M329 Host/Request Mode/General Runtime 紧凑测试 `10/10`，答案上下文与相邻回归 `15/15`，阶段收口回归 `18/18`；真实模型
  普通回答、经济工具链、Web 降级、工具提案和同一 Run 恢复均完成；Docker HTTP 默认通用入口、显式 Domain、preview、async、
  events、Artifact、SSE 续传和前端 smoke 验证通过。
- M330-A 显式真实模型验收通过：`COMPLETED`、`general`、`answer`、0 工具步骤、live-model answer evidence、答案非空且未命中
  内部引用标记；只保留脱敏状态和计数。
- M330-B Docker 紧凑测试 `23/23` 通过；覆盖 M330-A、M329 通用入口/Host/答案回归和结果类型推导。真实模型能力选择验收为
  `COMPLETED`、`general`、`mixed`、1 个已完成工具步骤、`economic_catalog_result`、live-model answer evidence；不保存原文。
- M330-C Docker 紧凑测试 `15/15` 通过；显式提案验收在 60 秒有界 HTTP 时限下通过，审批前 `WAITING_FOR_DECISION`/0 步，
  批准后同一 Run `COMPLETED`/1 步/答案流开启；30 秒重试仅记录为 provider 延迟。
- M330-D 门禁通过：Docker compileall、architecture strict、readiness/home `200`、结果投影 smoke 和 RunEvent smoke 通过。
- M330-E 合并紧凑回归 `31/31` 通过；默认 `/runs` 真实模型直答为 `general`/`COMPLETED`/`answer`/`direct_answer`，
  默认异步 HTTP/SSE/Artifact 验收通过；代码/文档索引均为 `333` 个源码文件、语义覆盖 `100%`。
- M330-F 已完成交接、索引和阶段交付；下一阶段规划入口切换为 M331-0。
- M331-C 已完成：上下文超预算时先压缩版本化 workflow template 摘要，再执行整体省略；Docker 恢复紧凑回归 `24/24` 通过，覆盖上下文、SQLite/Artifact、RunEvent/SSE 和工具审批恢复。
- M331-D/E 已完成：新增领域无关答案质量 receipt；补齐 ReAct 事件的 Python/前端契约；答案流上限统一到 6000 字符。Docker 合并定向回归 `42/42`、Console answer/event/projection smoke、compileall、architecture strict 和服务 smoke 通过；真实模型直答流式验收通过。

## 阻塞与下一步

- 阻塞：无；Docker GIS provider 因当前挂载数据不完整保持局部 unavailable，通用 Runtime 已按契约降级，未影响经济、指标、
  文本和通用直接回答。
- 下一步：提交推送 M331 阶段版本；恢复时只读取 M331 handoff、当前状态和本任务必要文件。
