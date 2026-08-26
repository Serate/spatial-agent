# M306 通用开放请求与多组件组合能力图

## 背景

M305 已验证 provider-backed Planner 可以形成合法的单组件 Composite 计划，并通过统一 receipt、TaskPlan、ToolRegistry、workflow、execution binding 和跨入口证据闭合。项目当前更大的全局短板不是继续增加 provider 诊断，而是让开放式问题更稳定地完成“请求事实 → 能力发现 → 多组件分解 → 数据交接 → 组合结果”。

## 能力模块

| 模块 ID | 责任 | 依赖 |
| --- | --- | --- |
| request-capability-bridge | 将自然语言请求事实、数据就绪和能力目录形成可解释的候选/缺口投影 | M305 receipt、RequestFacts、Capability Catalog |
| component-composition | 将开放问题分解成有界组件、依赖和 typed input reference，并维持 canonical identity | request-capability-bridge、Composite contract |
| execution-closure | 将合法组件集合闭合到 Workflow、TaskPlan/DAG、ToolRegistry 和 execution binding | component-composition、Domain Pack |
| result-composition | 按 Result/Data Profile/Evidence 合并多类型结果，形成用户可读答案和动态 View | execution-closure、Result Registry |
| acceptance-replay | 用脱敏 replay、真实 Docker 数据和跨入口对照验证组合成功/澄清/拒绝/恢复 | 上述模块 |

## 构建顺序

`request-capability-bridge → component-composition → execution-closure → result-composition → acceptance-replay`

每个模块只新增公共边界或 Domain Pack 声明，不在 Runtime、HTTP 或前端添加区域、专题、固定问句分支。模块之间通过版本化结构契约交接；模型输出不能直接获得执行授权。

## 全局不做

- 不引入 RAG、专题知识库或外部数据下载流程。
- 不为了演示多组件而扩大工具菜单；优先复用已有通用记录、栅格、矢量和指标能力。
- 不把模型的自然语言解释当作能力选择、执行计划或事实证据。
- 不把一次真实 provider 成功外推为全部开放问题成功。
