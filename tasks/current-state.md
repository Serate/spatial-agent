# 当前任务状态

> 热状态文件，只保留当前阶段和最近一个交接点，建议控制在 60 行以内。历史过程见
> `task-progress.md`，默认恢复不读取历史账本。

## 当前阶段

- 阶段：`M328`
- 当前任务：M328-E 阶段收口已完成
- 状态：已完成；等待提交并推送阶段版本
- 最近交付：M326 开放式 ReAct 稳定交付、真实 Docker/GIS 验收和跨入口恢复对照已完成

## 已完成

- M322 Python 工具提案、AST 校验、无网络 Docker sidecar 和待审批 receipt 已完成。
- 文档恢复架构重构方案已确定：热索引、阶段包、稳定知识、历史归档四层。
- 文件功能索引生成器、校验器和恢复主题查询已接入，覆盖 299 个源码文件。

## 已完成

- M328-B 已完成：统一 Web provider、HTTPS/白名单/重定向/大小/超时约束，补齐成功、无结果和网络不可用的
  `document_evidence` 投影；真实网络不可达时保持 `unavailable`，不伪造来源。
- M328-C 已完成：真实模型验证经济/指标多步组合、真实本地数据、白名单 Web 搜索和沙箱工具提案恢复；GIS 或网络
  不可用时保留结构化降级，不伪造空间结论。
- M328-D/E 已完成：前端/答案流、审批恢复、Artifact、轮询、SSE Last-Event-ID 和 Docker 收口门禁均通过。

- M323-A～D 已完成；审批状态、SQLite 恢复、Registry gate 和 HTTP 语义已闭合。
- M324 已完成：Runtime 创建时从 approval store 读取 approved 记录，仅通过 Registry 发布；handler 不可用时返回 degraded，不读取源码；前端消费版本化审批可见投影。
- P2 Persistence 已迁移至 `agent/persistence/`，根路径保留单向兼容 facade。
- P3 Provider Integration 已迁移至 `agent/integration/`，根路径保留单向兼容 facade。
- M323 修复了测试复用生产 SQLite 状态、SQLite 恢复丢失 definition、过期状态筛选遗漏三个问题，并补充回归覆盖。
- M325 修复了非策略类 ReAct 后续动作校验失败不能利用已有证据安全收束的问题。
- M326 已完成：开放 ReAct 不再继承自动模板的步骤/工具限制；Result、evidence、Artifact、SSE 和答案层统一表达部分结果；
  Artifact 原子发布、Provider 空响应错误边界和 live 验收判定已收口。
- M327 已完成全局重规划、Capability Map、Spec 和 Plan；首批任务是建立通用 capability descriptor，不引入 RAG 或自动工具上线。
- M327-A 已完成：新增版本化 descriptor 投影并接入统一 capability catalog；M327-A Docker 定向回归 `28/28` 通过。
- M327-B 实现已完成：Planner context 接入有界 descriptor 摘要；新增并接入版本化能力选择 evidence，覆盖正常选择、
  澄清、不可用和失败结果，不传播 Prompt、模型原文或工具参数。
- M327-B 已验证并收口：专项 `8/8`、相邻 Result/Evidence/Async/Selection 回归 `21/21`、规则 Runtime 实际链路、
  compileall、architecture strict 和文档/源码索引校验通过。
- M327-C 已冻结摘要契约：`spatial-agent.result-summary.v1`，统一投影 typed sections、completeness、限制和 evidence，
  供 Composite View 与答案生成共用。
- M327-C 已完成：公共 Result、Composite View 和答案生成 context 已接入 `result_summary`；Docker 专项与受影响回归通过。
- M327-D 已完成：同步、异步、Artifact、恢复和 Composite evidence 共享 `result_summary`；Console 已接入
  领域中立摘要渲染，地图/图表保留为可选 View。
- M327-E 已完成：修复 live probe 预算和 ReAct proposal 提示问题；Docker 紧凑回归 `66/66`、readiness `200`、
  compileall、architecture strict 和前端 smoke 通过；真实 Composite、经济+Web 搜索降级、sandbox proposal
  审批等待和答案流均完成脱敏验收。
- M328 已完成：入口为 `docs/stages/M328/{capability-map.md,spec.md,plan.md,handoff.md}`；下一阶段需重新进行全局规划，
  不从单一数据集细节继续扩展。

## M328-A 已完成

- 缺口：提案运行进入 `WAITING_FOR_DECISION` 后，审批接口目前只改变 approval/Registry 状态，未恢复原 run。
- 结果：审批 record/store 保存 run identity；ToolRegistry binding 刷新 execution-policy allowlist；Runtime React 从安全历史继续同一 run；Service approval 接口完成发布、恢复、拒绝关闭与统一结果投影。
- 修改：`agent/tooling/approval.py`、`agent/tooling/rehydration.py`、`agent/tools.py`、`agent/react/loop.py`、`agent/runtime_core/react_runtime.py`、`agent/runtime_core/execution_policy.py`、`agent/runtime_core/tool_approval_resume.py`、`agent/runtime_core/run_lifecycle.py`、`agent/runtime.py`、`agent/application/run.py`、`agent/service.py`、`tests/test_m328_tool_approval_resume.py`。
- 验证：Docker M328-A `3/3`；M322/M323/M324 相邻回归 `26/26`；compileall 通过。
- 下一步：M328-B 统一 Web evidence provider/allowlist/失败状态投影。

## 必要文件

- `docs/stages/M328/plan.md`
- `docs/stages/M328/handoff.md`
- `agent/tooling/approval.py`
- `agent/react/loop.py`
- `agent/runtime.py`
- `tests/test_m323_tool_approval.py`
- `tests/test_m324_tool_governance.py`
- `scripts/console_result_projection_smoke.js`
- `scripts/validate_document_index.ps1`
- `scripts/validate_code_index.ps1`
- `docs/document-index.json`
- `docs/code-index.json`

## 验证

- M326 Docker 阶段紧凑回归 `49/49`、Artifact/Provider 定向回归、compileall、architecture strict 和 readiness `200` 通过。
- 真实 Docker/GIS：sync/async/polling/artifact/evidence/SSE/Last-Event-ID/restart 对照通过；真实数据仅一次性只读挂载。
- M327-E：真实 Composite `gis + economic` 两组件完成；真实 Web `web_search` 命中并因网络不可达安全降级；
  proposal 真实模型生成后 sandbox validated 并停在 `WAITING_FOR_DECISION`；答案流分别为 `512/331 answer_delta`。

## 阻塞与下一步

- 阻塞：无。
- 下一步：提交并推送 M328；随后按全局目标规划下一阶段。恢复时只读取本快照、任务状态尾部、M328 交接和新阶段
  明确列出的文件。

## M328-C 当前交接

- 目标：通过一次或少量受控真实模型请求覆盖多领域、多步骤、本地数据、Web 搜索和沙箱工具提案；记录每个行动的
  脱敏状态、动作计数、结果完整性、来源状态和答案流，不保存 Prompt、模型原文、网页正文或密钥。
- 已完成：审批恢复闭环、动态 Registry 工具刷新、稳定 Runtime context 指纹、Web evidence 失败投影和真实经济多步
  降级验收已完成；真实动态工具已完成生成、sandbox 校验、审批、同一 Run 恢复和实际执行。
- 已验证：真实指标/经济/数据组合；本地数据 + `web_search` 的 4 步请求；`propose_tool` 审批恢复；SSE/Last-Event-ID、
  答案流和部分结果均保持可读。
- 失败边界：Web 不可达只能记录 `unavailable/search_network_error`；GIS 数据缺失只能返回 `data_unavailable` 或
  `partial`，不能凭空生成空间结论；Provider 非法 JSON 不能被判为 live 成功。
- 必要文件：`scripts/live_provider_probe.py`、`scripts/live_tool_proposal_acceptance.py`、
  `tests/test_m328_tool_approval_resume.py`、`tests/test_m328_web_evidence.py`、`agent/llm_planner.py`、
  `agent/react/loop.py`、`agent/runtime_core/react_runtime.py`。

## M328 收口验收

- 紧凑回归：M322/M323/M324/M328 共 `32/32`；离线 smoke 通过。
- 门禁：Docker 重建并健康运行；readiness `200`；compileall、architecture strict、代码索引和文档索引通过；前端结果投影 smoke 通过。
- 真实模型：经济本地数据 + `web_search` 完成 4 个工具步骤，`COMPLETED`，SSE 共 420 事件且 Last-Event-ID 续传 419 事件；
  Web 不可达时证据标为 `unavailable/search_network_error`。
- 真实跨域：经济目录 + 区域指标目录由 LLM 规划为 2 个组件，均 `COMPLETED`，Artifact/evidence 可用。
- 真实工具提案：审批前 0 工具步骤；审批后 `approved_resume` 保持同一 Run，动态工具实际执行 1 次并 `COMPLETED`。
- 一次过宽请求按设计返回结构化澄清/拒绝：缺少具体指标或模型字段漂移时不创建执行 Run；这不是成功验收路径，也不伪造结果。
