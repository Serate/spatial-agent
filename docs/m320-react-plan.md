# M320 ReAct 循环实施计划

> 状态：已完成。M320-A～F 已完成阶段实现、精简验收和交付准备；真实模型已
> 到达 Provider 并执行 GIS 首动作，但本次 live 未完成全链路，按安全边界记录为
> live backend failure。恢复入口为
> [`docs/agent-work-state.md`](agent-work-state.md)，任务账本为
> [`tasks/task-progress.md`](../tasks/task-progress.md)。

## 阶段状态与任务

### M320-A：契约与状态骨架 — 已完成

- 建立能力图、Spec、Plan 和本阶段交接入口。
- 扩展 `RunEvent` 的 ReAct 事件字段。
- 为 `AgentRunResult` 和 SQLite 恢复增加安全的 ReAct evidence 投影。
- 为 `ToolRegistry` 提供参数校验和结果类型读取 seam。
- 阶段代码已纳入 M320 版本提交；Docker 契约和静态门禁结果见 M320-E。

### M320-B：决策适配器 — 已完成

- 为 `LLMPlanner` 增加 `decide()`，复用 OpenAI-compatible structured JSON 传输。
- 提供 ReAct 专用、边界清晰的决策输入：请求事实、能力/策略摘要、上一轮安全结果引用和预算。
- 兼容 fake/replay client，不改变既有 `plan()` 契约；计划和动作参数先完整校验，再进入事件或执行。
- 不保存或展示 Prompt、模型原文、隐藏思维链或敏感字段。
- 结果：`LLMPlanner.decide()` 已复用 structured JSON client，并按 Planner/Runtime
  工具 allowlist 交集限制动作；上下文和历史采用有界脱敏投影，兼容只实现两参数
  `complete_json()` 的 fake/replay client。
- 验证：Docker M320-B 紧凑契约 **4/4** 通过，`git diff --check` 通过；未调用真实模型。

### M320-C：通用 ReActLoop — 已完成

- 每轮只接受一个 `call_tool`、`ask_clarification`、`finish` 或 `reject` 动作。
- 统一轮次、动作、deadline、取消、重复签名、空转和预算保护。
- 工具调用只经过 ToolRegistry、schema、权限、数据 readiness、重试和取消门禁。
- 将工具结果压缩为安全摘要和 `result_ref` 供下一轮决策；`search`/`propose_tool` 在 M320 仅返回结构化不可用状态。
- 验证：Docker M320-B/C 紧凑契约 **8/8** 通过，覆盖单步后 finish、多轮安全历史、
  重复动作、动作预算、澄清和拒绝；未调用真实模型。

### M320-D：Runtime 接入 — 已完成

- 首轮决策进入既有 plan/validate 边界，后续每轮只物化并执行一个 `StepRun`。
- 复用现有 Result、RunEvent、answer generator 和答案 token 流；记录轮次、动作、引用、失败原因和最终 evidence。
- 统一澄清、拒绝、取消、失败、有限恢复和终态投影；Rule/Replay 保持旧路径和测试兼容。
- 不让 ReAct 绕过 Execution Policy、Domain validator、ToolRegistry 或现有恢复契约。
- `run_lifecycle.py` 仅保留阶段选择，具体 ReAct bridge 收敛到
  `agent/runtime_core/react_runtime.py`，避免重新形成 God method。
- ReAct 决策获得有界工具契约摘要；兼容宽松 `json_object` Provider 的额外字段和
  可选空值只做有限 envelope 修复，动作参数仍由 Runtime 完整校验。

### M320-E：精简验收 — 已完成

- 新增 `tests/test_m320_react_runtime.py`，合并覆盖简单 finish、单步、多步、澄清/拒绝、非法动作、重复动作、预算保护和安全 evidence 的最小契约。
- Docker 中集中执行 M320 契约、受影响 Runtime 回归、compileall 和 architecture strict。
- M320 契约 **14/14**，M131/M133/M135 相邻回归 **22/22**，compileall 和
  architecture strict 通过。
- 真实模型 + Docker/GIS 只做显式单次验收：Provider 使用 `chat_completions`/
  `json_object` 成功返回决策并执行 `get_dataset_health_report`，随后因真实运行链路
  的 backend failure 未完成用例；未保存 key、Prompt、模型原文或敏感原始数据。
- 测试替身覆盖了直接 finish、单/多步依赖、非法参数阻断、重复/预算保护、澄清/拒绝、
  SQLite reopen 和安全 evidence；默认 CI 仍保持离线。

### M320-F：交付与全局重规划 — 已完成

- 更新任务账本、当前快照、中文问题日志（仅有新问题时）和总计划。
- 记录验证结果、阻塞、未提交文件和恢复入口；完成后提交并推送一个阶段版本。
- 阶段结束按产品、架构、数据、模型、部署、体验和测试七个维度重新规划 M321-M325，
  不陷入单个 GIS 数据集细节；下一入口为 M321 白名单搜索执行器。

## 当前执行顺序

1. [x] 完成 M320-D 的 Runtime bridge、事件/evidence 和答案流收口。
2. [x] 只做受影响的静态/契约检查；M320-E 集中执行阶段验收。
3. [x] 更新交接文档并完成版本交付和全局重规划。

## 固定边界

- 单 Agent，最大并发度 1；Python、GIS、测试和验收使用 Docker。
- M320 不实现白名单网页抓取、Python 工具生成、审批注册或前端大改；分别留给 M321-M323/M324。
- 默认真实模型走受控 ReAct；Rule/Replay 只用于离线确定性路径或显式降级。
