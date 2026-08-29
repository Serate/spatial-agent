# Agent 当前工作快照

> 这是默认恢复入口，必须保持短小，只记录当前阶段。历史阶段、完整计划和问题记录不放在这里。
> 默认恢复命令：`pwsh -NoProfile -File scripts/resume_context.ps1`。

## 当前目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime；真实模型默认通过受控 ReAct
理解开放式问题、发现能力、调用工具、搜索白名单网页、汇总证据并流式回答。GIS 只是业务载体。

## 当前阶段

- 阶段：`M328`
- 当前任务：M328-C 跨域开放行动验收
- 状态：进行中；M328-B 已完成
- 最近交付：M326 已完成开放式 ReAct 稳定交付、真实 Docker/GIS 验收和跨入口恢复对照
- 协作：单 Agent，最大并发度 1；Python、GIS、测试和阶段验收优先使用 Docker
- M326 已完成：开放 ReAct 与自动 Domain 模板策略解耦；Result/evidence/artifact/SSE/答案统一表达部分结果；
  Artifact 原子发布和 Provider JSON 错误边界已修复；真实模型 + Docker/GIS 多步与矢量请求完成安全验收。
- M327-A 已完成：新增 `spatial-agent.capability-descriptor.v1`，从现有 Domain Catalog 生成有界的输入事实、输出类型、
  前置条件、证据要求、执行工具、成本提示和可用性投影；未知版本或缺少身份的 descriptor fail closed。
- M327-B 实现已完成：Planner context 接入有界 descriptor 摘要；新增 `spatial-agent.capability-selection.v1`
  选择 evidence，统一 chosen/candidate/missing facts/reason code，并接入 plan、失败、Result、异步和 evidence registry；
  不传播 Prompt、模型原文或工具参数。
- M327-B 已验证并收口：专项 `8/8`、相邻 Result/Evidence/Async/Selection 回归 `21/21`、规则 Runtime 实际链路、
  compileall、architecture strict 和文档/源码索引校验通过。
- M327-C 契约已冻结：新增 `spatial-agent.result-summary.v1`，由公共 Runtime 从 Result completeness、typed sections
  和 evidence 生成有界 blocks；答案 context 与 Composite View 共用该投影，不传播 Prompt、模型原文、工具参数、路径、
  几何 features 或密钥。
- M327-C 已完成：摘要投影已接入公共 Result、Composite View 和答案生成 context；离线专项 `4/4`，受影响紧凑回归 `26/26`，
  答案流相邻回归 `5/5`，Docker compileall/architecture/index 校验通过。
- M327-D 已完成：同步 Result、异步结果证据、Artifact、恢复证据和 Composite evidence 共享同一
  `spatial-agent.result-summary.v1`；Console 优先动态展示领域中立摘要，View 仍是可选 renderer。
- M327-E 已完成：修复 live probe 的 4096 token 隐性上限和 ReAct proposal 提示冲突；真实 Docker 验收覆盖
  GIS+经济 Composite、多步本地经济+白名单 Web 搜索降级、真实 sandbox 工具提案审批等待和答案流。
  Docker 紧凑回归 `66/66`，readiness `200`，真实答案流产生 `512/331` 个 `answer_delta`；未保存敏感内容。
- M327 目标：完善通用能力描述、选择解释和跨类型结果摘要，不为固定区域、问句或 GIS 页面增加专用分支。

## 下一阶段

- 阶段：`M328` 受控开放行动闭环
- 状态：M328-C 进行中：跨域开放行动验收
- 入口：[`stages/M328/capability-map.md`](stages/M328/capability-map.md)、[`stages/M328/spec.md`](stages/M328/spec.md)、
  [`stages/M328/plan.md`](stages/M328/plan.md)、[`stages/M328/handoff.md`](stages/M328/handoff.md)
- 当前任务：验证经济、区域指标和 Web 搜索的多步组合；处理数据缺失时的结构化降级。

## 当前阶段入口

- 当前阶段能力图：[`stages/M328/capability-map.md`](stages/M328/capability-map.md)
- 当前阶段 Spec：[`stages/M328/spec.md`](stages/M328/spec.md)
- 当前阶段 Plan：[`stages/M328/plan.md`](stages/M328/plan.md)
- 当前阶段交接：[`stages/M328/handoff.md`](stages/M328/handoff.md)
- 任务状态：[`../tasks/current-state.md`](../tasks/current-state.md)
- 文档索引：[`document-index.json`](document-index.json)

## 当前任务必要文件

- `docs/stages/M328/handoff.md`
- `docs/stages/M328/spec.md`
- `docs/stages/M328/plan.md`
- `agent/network/web_search.py`
- `agent/result_summary.py`
- `agent/answer_generation.py`
- `agent/application/composite_view.py`
- `tests/test_m321_web_search.py`
- `tests/test_m327_result_summary.py`
- `tests/test_m313_answer_stream.py`
- `agent/application/composite_planner.py`
- `agent/llm_planner.py`
- `tests/test_m304_provider_runtime.py`
- `tests/test_m320_react_runtime.py`
- `scripts/validate_document_index.ps1`
- `scripts/validate_code_index.ps1`
- `docs/document-index.json`
- `docs/code-index.json`

## M328-A 当前交接

- 状态：已完成；目标是提案审批后恢复原等待运行，审批前不执行，且只允许同一 receipt fingerprint/version 的绑定继续。
- 已确认缺口：`RuntimeReactExecution` 只创建 `WAITING_FOR_DECISION` 的 approval receipt；`resolve_tool_approval` 当前只发布/撤销 Registry 绑定，不恢复等待运行。
- 当前修改范围：`agent/tooling/approval.py`、`agent/tools.py`、`agent/runtime_core/react_runtime.py`、`agent/runtime_core/react_resume.py`（待新增）、`agent/runtime.py`、`agent/service.py`、对应紧凑测试。
- 完成：approval record/store 保存 run identity；RuntimeToolApprovalResume 接通批准/拒绝/撤销/过期；ReAct 支持安全历史续跑；Service approval 入口完成统一结果投影。
- 验证：Docker M328-A 专项 `3/3`，相邻 M322/M323/M324 回归 `26/26`；真实模型 proposal 审批闭环待阶段显式验收。
- 下一步：进入 M328-B Web evidence 可用性；实现后再进行本轮多领域真实模型回答测试。

## M328-B 当前任务

- 目标：统一 Web provider、HTTPS/白名单、重定向、大小和超时的安全投影；让成功、无结果和网络不可用
  共享 `document_evidence` 结果契约，并由答案/前端显示来源状态与限制。
- 当前状态：代码审计与最小契约实现进行中；真实 Web/模型验收尚未开始。
- M328-B 已完成：文档证据保留安全 source record、status/reason_code/query/allowlist；前端可显示来源状态、
  标题、域名和受限摘要，并对无结果/不可用生成不同限制。
- 下一步：完成跨域真实回答与工具提案审批恢复验收；最终覆盖本轮用户要求的多领域、多步骤、
  本地数据、Web 搜索、工具提案审批恢复和流式答案。

## 最近验证

- M326 Docker 阶段紧凑回归 `49/49`、Artifact/Provider 定向回归、compileall、architecture strict 和 readiness `200` 通过。
- 真实 Docker/GIS：sync/async/polling/artifact/evidence/SSE/Last-Event-ID/restart 对照通过；真实数据仅一次性只读挂载。
- 未保存 Prompt、模型原文、密钥或敏感数据。
- M327-A Docker 定向回归 `28/28` 通过；未修改 Runtime 生命周期。
- M327-B Docker 定向回归 `8/8`、相邻回归 `21/21`、规则 Runtime 实际链路、compileall、architecture strict 和索引校验通过。
- M327-D Docker 定向回归 `16/16`、跨入口摘要一致性 `2/2`、前端 projection smoke、compileall 和 architecture strict 通过。
- M327-E Docker 受影响回归 `66/66`；compileall、architecture strict、readiness `200` 和 Console projection smoke 通过。
- 真实 Composite：`gis + economic` 两组件均完成，结果含 `composite/vector/metrics`；Artifact 与 result summary 可读。
- 真实 Web：`web_search` 实际执行并安全返回 `search_network_error/unavailable`，本地经济工具继续完成且未伪造来源。
- 真实 proposal：receipt `validated`，运行进入 `WAITING_FOR_DECISION`，未执行、未发布，receipt 不含 source/example。
- 真实答案流：两次运行分别产生 `512`、`331` 个 `answer_delta`，均可通过 SSE 回放至 terminal。

## 恢复规则

1. 先读取本文件、`document-index.json`、`tasks/current-state.md` 和当前阶段 handoff。
2. 只按当前阶段 Plan 的当前批次读取明确列出的源码；M327 已完成，不读取其实现源码，除非验收失败。
3. 需要查历史时使用 `resume_context.ps1 -Topic ...`，需要归档时显式增加 `-IncludeHistory`。
4. M323～M327 已完成；恢复时只读取本快照、当前阶段 handoff/plan/spec 和明确源码。
