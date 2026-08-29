# M327 阶段交接

## 状态

- 阶段：`M327` 开放请求能力发现与结果质量
- 状态：已完成
- 当前任务：M327-E Docker 验收与阶段收口（已完成）
- 恢复入口：优先读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本文件和 `plan.md` 中当前批次；不读取完整历史

## 已完成

- 已从产品体验、Runtime 架构、Domain 扩展、数据、模型、部署和测试七个维度完成全局重规划。
- 已建立 Capability Map、Spec 和分批 Plan；首版不引入 RAG、自动数据下载或模型生成工具自动上线。
- M327-A 已完成：新增 `spatial-agent.capability-descriptor.v1`，从现有 Domain Catalog 生成有界的输入事实、
  输出类型、前置条件、证据要求、执行工具、成本提示和可用性投影；未知版本或缺少身份的 descriptor fail closed。

## 进行中

- M327-B 已完成：Planner context 使用有界 descriptor 摘要，并记录
  `spatial-agent.capability-selection.v1` 脱敏选择解释。
- M327-C 契约已冻结：公共 `spatial-agent.result-summary.v1` 由 Result completeness、typed sections、Evidence 和限制
  生成统一的 `blocks`；首版覆盖 vector/raster/metrics/timeseries/text/document_evidence/composite，并明确排除 Prompt、
  模型原文、工具参数、路径、几何 features 和密钥。
- M327-C 已完成：`agent/result_summary.py` 已接入公共 Result、Composite View 和答案生成 context；答案提示明确优先结论、
  关键发现、限制与 evidence，技术 facts 作为有界详情。
- M327-D 已完成：同步 Result、异步结果证据、Artifact 顶层、恢复证据和 Composite evidence 现在消费同一份
  `spatial-agent.result-summary.v1`；响应顶层提供同值便利别名，Artifact 不重新生成第二份摘要。
- M327-D 已完成：Console 先渲染统一摘要的结论、关键发现、结果明细、限制和证据来源，再挂载可选 View renderer；
  普通 Result 和 Composite Result 均可动态展示，复杂事实不会退化成 `[object Object]`。
- M327-E 已完成：修复 live probe 的隐性 4096 token 上限和 ReAct proposal 提示冲突；真实 Docker 验收覆盖
  GIS+经济 Composite、多步本地经济+白名单 Web 搜索降级、真实 sandbox proposal 审批等待和答案流。

## 必要文件

- `docs/stages/M327/plan.md`
- `scripts/live_provider_probe.py`
- `agent/application/composite_planner.py`
- `agent/llm_planner.py`
- `tests/test_m304_provider_runtime.py`
- `tests/test_m320_react_runtime.py`
- `tests/test_m327_cross_entry_projection.py`
- `scripts/console_result_projection_smoke.js`
- `scripts/live_http_acceptance.py`
- `scripts/validate_document_index.ps1`
- `scripts/validate_code_index.ps1`
- `docs/document-index.json`
- `docs/code-index.json`

## 验证与边界

- M326 阶段 Docker 紧凑回归 `49/49`、compileall、architecture strict、readiness `200` 和真实 Docker/GIS 验收已完成。
- M327-A Docker 定向回归 `28/28` 通过（descriptor、既有 requirements、Domain Catalog 和兼容目录契约）。
- M327-B Docker 定向回归 `8/8` 通过；相邻能力/evidence/async/selection 回归 `21/21` 通过；规则 Runtime
  选择 identity 实际检查、compileall、architecture strict 和索引校验通过。
- M327 继续采用单 Agent、最大并发度 1；Python、GIS、测试和阶段验收优先在 Docker 中运行。
- 不提交 API key、Prompt、模型原文、真实数据和临时输出。
- M327-D Docker 定向回归 `16/16`、Artifact/恢复/异步摘要一致性 `2/2`、前端 projection smoke、
  compileall 和 architecture strict 已通过；strict 仅保留 `agent/runtime.py`、`agent/service.py` 的既有 God module 警告。
- M327-E Docker 受影响回归 `66/66`、readiness `200`、compileall、architecture strict 和 Console projection smoke 通过。
- 真实 Composite 规划/执行：`gis + economic` 两组件均完成，结果含 `composite/vector/metrics`，Artifact 和
  `spatial-agent.result-summary.v1` 可读取。
- 真实 Web：`web_search` 实际执行并返回 `search_network_error/unavailable`，本地经济工具继续完成，未伪造来源；
  HTTP/Artifact/SSE/Last-Event-ID 对照通过。
- 真实 proposal：receipt `validated` 后运行进入 `WAITING_FOR_DECISION`，未执行、未发布，receipt 不含 source/example。
- 真实答案流：两次运行产生 `512`、`331` 个 `answer_delta`，均回放到 terminal。

## 下一步

进入 `M328`。优先从审批后的运行恢复闭环开始，再处理 Web evidence 可用性、跨域开放行动和恢复体验；
恢复时只读取 M328 handoff/plan/spec 与当前批次明确文件，不重新读取 M327 全量实现或模型输出。
