# M320 ReAct 循环 Spec

## 1. 公共契约

### 1.1 决策

模型每次只能返回一个 `spatial-agent.react-decision.v1` 对象。`call_tool` 必须
包含已登记的 `tool_name`、对象类型 `arguments`，并在进入执行前再次通过对应
ToolRegistry input schema；`output_type` 表示当前任务预期的公共结果类型。

`ask_clarification` 和 `reject` 必须包含有界用户可读 `message`；`finish` 必须
包含安全完成摘要，不能携带工具参数。`search` 和 `propose_tool` 只通过策略开关
和后续能力模块，M320 不产生实际副作用。

### 1.2 循环结果

ReAct 循环返回有界结果：

- `finished`：收到 `finish`，可进入现有 answer 阶段；
- `clarification`：等待用户补充事实；
- `rejected`：请求被策略拒绝；
- `blocked`：决策非法、动作不可用、预算耗尽或工具执行失败。

结果包含动作数、轮次数、最后动作、原因码和 `react-evidence.v1` 轮次列表。
结果摘要只能包含结果类型、状态、引用、计数、指标摘要和有界 warning，不带原始
参数、源代码、Prompt、完整异常或大段几何/栅格内容。

### 1.3 RunEvent

沿用 `run-event.v1`，增加以下可恢复事件：

- `react_turn_started`
- `react_action_accepted`
- `react_action_completed`
- `react_action_blocked`
- `react_finished`

事件数据只允许 `turn_index`、`action`、`action_id`、`validation_state`、
`result_ref`、`output_type`、`action_count`、`max_actions`、`max_turns`、
`reason_code` 和 `summary` 等有界字段。

## 2. 生命周期

1. `resolve/clarify` 建立当前请求和安全上下文。
2. `plan` 阶段请求第一轮决策；第一条工具动作物化为一个 TaskPlan，并经过
   Domain validator、ToolRegistry 名称和 Execution Policy 校验。
3. `execute` 阶段执行一个动作，记录 StepRun；结果只以安全摘要和引用进入下一轮
   决策上下文。
4. 下一轮只能追加一个动作；追加前重新验证完整 TaskPlan 的依赖、工具、结果类型、
   Domain policy 和动作预算。
5. `finish` 后复用既有 answer generator/answer delta 流；其余状态由现有失败和澄清
   生命周期收口。
6. 每次阶段保存后都可通过既有内存/SQLite RunEvent 和 Result 查询；实时事件丢失
   不得使核心运行失败。

## 3. 安全与恢复

- 重复动作签名、空转和轮次/动作/deadline 超限均 fail closed。
- 工具调用永远不绕过 Registry、参数 schema、权限、数据 readiness、重试和取消。
- 真实模型的结构化响应先归一化，再写入事件或执行；非法 JSON 不得执行。
- 已完成 StepRun 和 ReAct evidence 与结果一起持久化；重启/轮询只消费安全契约。
- M320 暂不自动恢复未完成的模型决策；运行失败保留可读 reason code，后续 M324
  补齐跨进程继续决策。

## 4. 验收

- 简单请求可一轮 `finish`，不产生无意义工具调用。
- 单步和依赖多步请求分别产生 1 和多轮事件，后轮能看到前轮结果引用。
- 非法工具、非法参数、重复动作、预算耗尽、取消和 deadline 均不越过执行门禁。
- 澄清、拒绝和搜索/提案降级具有结构化状态且不产生副作用。
- Rule/Replay 回归保持原行为；真实 OpenAI-compatible Planner 只在阶段收口显式调用
  一次，失败保留安全 provider receipt。
