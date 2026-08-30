# M330 阶段交接

## 状态

- 阶段：`M330` 通用 Agent 开放问题质量与纵向行为验收
- 状态：M330 已完成并交付；恢复入口切换到 M331-0
- 基线：M329 完成后的工作区版本待提交
- 协作：单 Agent，最大并发度 1；测试、真实模型和 GIS 优先使用 Docker

## 当前目标

验证 general Runtime 能处理非预定义的多领域问题，并把直接回答、能力发现、受控行动、澄清、降级、恢复和答案体验连成
用户可感知的 Agent 行为。当前不引入 RAG，不新增固定领域分支。

## 已完成

- M329 已将产品 `/runs`、preview、async、events、Artifact 和 CLI 默认切换到 `general` Runtime；显式 Domain 入口不变。
- M329 已验证真实模型直接回答、经济工具链、白名单 Web 降级、工具提案审批和同一 Run 恢复。
- M329 已完成 SQLite/Artifact 重启、多轮续问、SSE `Last-Event-ID`、Docker 精简回归和答案上下文状态修复。

## M330-0 验收

- 已建立 `capability-map.md`、`spec.md`、`plan.md` 和本 handoff。
- 已建立 `direct-answer-scenarios.md`，固定概念解释、比较、总结、写作和简单计算的公共投影；不读取完整历史或模型原文。

## M330-A 实现

- 答案生成提示明确允许不依赖外部数据的通用知识、比较、总结、写作和简单算术直接使用用户请求回答，避免因事实包为空而误报
  “没有结果”；实时、地域和专门外部事实仍必须受证据约束。
- `tests/test_m330_direct_answer.py` 覆盖五类场景的 general Rule Runtime、`request_mode=answer`、0 工具步骤、模型答案上下文
  和领域中立离线 fallback；Docker 测试 `4/4` 通过。
- 当前尚未记录模型原文；显式真实模型验收只保留状态、模式、工具计数、答案非空和安全检查结果。

## M330-A 收口

- Docker M330-A 紧凑测试 `4/4`，答案生成与通用入口相邻回归 `14/14` 通过。
- 显式真实模型验收通过：`COMPLETED`、`general`、`request_mode=answer`、0 工具步骤、`direct_answer`、live-model
  answer evidence、答案非空且未命中内部引用标记；不保存模型原文。

## 必要文件

- `agent/general_runtime.py`
- `agent/general_capability_host.py`
- `agent/runtime_core/react_runtime.py`
- `agent/llm_planner.py`
- `agent/answer_generation.py`
- `agent/result_summary.py`
- `agent/run_events.py`
- `agent/application/http.py`
- `agent/service.py`
- `production_api.py`
- `serve_api.py`
- `run_demo.py`
- `web/src/console_result_projection.js`
- M330 紧凑测试及必要的现有 ReAct/答案/HTTP 测试

## 恢复规则

只读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本 handoff、M330 Plan 中当前子任务涉及的源码和测试。真实模型输出、
Prompt、密钥、完整历史和全量测试按需读取，不作为默认上下文。

## 阻塞与下一步

- 阻塞：无。
- 当前动作：M330 已交付；下一次恢复只读取热状态、M331-0 handoff 和 M331 规划入口，不读取 M330 全量源码或模型输出。

## M330-B 收口

- `GeneralCapabilityHost.result_type_for_tool` 从声明式 workflow blueprint 解析工具与操作对应的公共 Result 类型；
  `ToolRegistry` 和 ReAct 执行 seam 支持传入已校验参数。已存在的静态 schema 仍优先兼容。
- General Runtime 启用已发布 Result Registry 的严格 allowlist；模型自造的结果标签在执行前拒绝，可信目录推导优先于模型标签。
- Docker M330-B 紧凑回归 `23/23` 通过。真实模型能力选择返回 `COMPLETED`、`general`、`mixed`、1 个已完成工具步骤、
  `economic_catalog_result` 和 live-model answer evidence；不保存模型原文。

## M330-C 收口

- Docker M330-C 紧凑回归 `15/15` 通过，覆盖 Web evidence 的成功/无结果/不可用、Provider 健康降级、ReAct 预算/澄清/参数
  校验和工具提案审批恢复。
- 显式提案验收在 60 秒有界 HTTP 时限下通过：审批前 `WAITING_FOR_DECISION` 且 0 步，批准后同一 Run `COMPLETED` 且执行
  1 步，答案流开启；30 秒首次尝试仅记录为 provider 延迟，不改变安全结论。
- Web 网络不可达时返回结构化 unavailable/search_network_error，不伪造网页来源；proposal 始终经过 sandbox + 人工审批。

## M330-D 收口

- Docker compileall、architecture strict（无 error，仅保留既有 runtime/service God module warning）、readiness/home `200`、
  `console_result_projection_smoke.js` 和 `console_run_events_smoke.js` 均通过。
- 默认 `/runs` 真实模型直答返回 `general`、`COMPLETED`、`request_mode=answer`、`direct_answer` 和 live-model answer evidence；
  `/runs/auto` 仍保留自动 Domain 选择语义，不与默认通用入口混用。

## M330-E 收口

- Docker 阶段合并回归 `31/31` 通过；compileall、architecture、代码/文档索引、readiness、smoke 和前端投影门禁通过。
- 真实验收覆盖：通用非数据直答、目录能力选择、Web 不可用降级、sandbox+人工审批同一 Run 恢复、默认 HTTP 异步/SSE/Artifact
  回放。所有报告只记录状态、模式、动作计数、结果类型、evidence 和事件序列。
- 本阶段未保存模型原文、Prompt、网页正文、工具源码、API key 或私有数据。下一阶段必须继续从全局目标重规划，不以单一领域细节扩展。

## M330-F 交付

- 热状态、当前任务、进度账本、里程碑、代码索引和文档索引已更新；M330 阶段版本已提交并推送，恢复入口切换到 M331-0。
- M330 完成标志：默认通用入口可直接回答非数据问题，可从能力目录选择已登记工具，受控搜索/提案/审批恢复/降级可观测，
  结果、证据、事件、SSE、Artifact 和前端投影保持公共契约。
- 下一阶段全局方向：提高真实模型在开放任务中的计划/工具/答案可靠性与可用率，继续保持 Domain-neutral Runtime、受控行动、
  脱敏证据和最小充分测试，不引入 RAG 或无边界执行。
