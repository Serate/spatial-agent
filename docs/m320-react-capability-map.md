# M320 ReAct 循环能力图

## 目标

把 M318 已冻结的 `spatial-agent.react-decision.v1` 接入真实模型运行时，形成
“决策一轮 → 校验一个动作 → 执行或安全降级 → 返回有限结果 → 再决策”的闭环。
GIS、文本和经济 Domain 只提供能力目录、工具和结果契约，公共 Runtime 不写专题
分支。

## 能力切片

| 切片 | 责任 | 复用的既有边界 |
| --- | --- | --- |
| react-decider | LLMPlanner 生成并校验一条 ReAct Decision | Provider structured JSON、Planner context |
| react-loop | 轮次、动作预算、重复/空转保护和结果摘要 | Execution Policy、RunControl |
| react-tool-bridge | 将一个 `call_tool` 绑定为 StepRun 并执行 | ToolRegistry、Domain preflight、重试、Result |
| react-evidence | 保存轮次、动作、引用和安全摘要 | RunEvent、AgentRunResult、artifact/SQLite |
| react-surface | 将 ReAct 事件投影到既有阶段、答案流和失败契约 | Result/View/Evidence、SSE/polling |

## 依赖关系

```text
LLMPlanner.decide
        ↓
ReActLoop ──→ RunControl / ExecutionPolicy
        ↓ call_tool
Runtime bridge ──→ ToolRegistry ──→ Domain preflight ──→ StepRun/Result
        ↓
safe result summary + result_ref ──→ next decision
        ↓
RunEvent + react-evidence.v1 ──→ CLI / HTTP / Console / recovery
```

## 本阶段范围

- 支持 `call_tool`、`ask_clarification`、`finish` 和 `reject`。
- `search`、`propose_tool` 识别并返回结构化降级，不执行网络访问、代码或注册。
- 默认真实模型使用 ReAct；Rule、Replay 和未显式启用的旧 LLMPlanner 继续使用
  TaskPlan 一次性规划路径。
- 每轮最多一个动作；默认最多 8 轮、12 个工具动作；运行时 deadline、取消和
  已有工具超时继续生效。

## 非目标

- 本阶段不实现白名单网页抓取（M321）。
- 本阶段不生成、运行或注册 Python 工具（M322/M323）。
- 不展示 Prompt、模型原文或隐藏思维链；只投影动作类型、工具名、结果引用和
  有界摘要。
