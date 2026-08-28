# M319 通用执行策略能力图

## 定位

M319 把 M318 建立的 `Execution Policy` 从静态契约接入现有 Runtime。执行策略是
能力发现、TaskPlan、ToolRegistry 和结果契约之间的公共门禁，不负责理解 GIS 或其它
专题语义，也不改变 ReAct 的实际循环实现（该部分在 M320）。

## 能力模块

| 模块 id | 职责 | 依赖 |
|---|---|---|
| policy-resolution | 根据计划、可选 workflow 和 Domain policy 解析 direct tool、generated DAG、Domain workflow 或 ReAct | Execution Policy、Capability Catalog、ToolRegistry |
| plan-gate | 校验工具、结果类型、动作数、依赖形状和高风险确认要求 | policy-resolution、TaskPlan/DAG |
| runtime-binding | 将同一策略用于同步、预览、重规划、异步和恢复证据 | plan-gate、Result/Evidence |
| compatibility | 保留旧 plan-policy、execution-binding 和跨入口投影的兼容形状 | runtime-binding、SQLite/artifact |

## 建设顺序

`policy-resolution → plan-gate → runtime-binding → compatibility`

## 固定边界

- 没有 workflow 不再自动阻断普通 direct tool 或通用 DAG；workflow 仍是可选的
  Domain 执行策略。
- Domain 可通过已有 `validate_workflow_plan`、`validate_plan` 和 `plan_policy` seam
  保留高风险约束、权限和数据 readiness 门禁。
- 所有工具仍必须经过 TaskPlan 通用校验、Domain preflight 和 ToolRegistry；策略解析
  不会注册或直接调用工具。
- `allowed_result_profiles` 只接受已声明的 Domain policy 结果类型；没有 Domain policy
  时保留已有通用 Runtime 兼容行为，由结果 Registry/Result Contract 在后续边界校验。
- M319 只落地策略解析和证据一致性，不提前实现 M320 的 ReAct 逐轮决策。
