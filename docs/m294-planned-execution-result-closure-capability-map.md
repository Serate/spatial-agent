# M294 已验证计划到执行/答案/证据闭合能力图

## 全局缺口

当前 Planner 已能生成并验证组件 TaskPlan/DAG，但 Composite submit 仍主要把 canonical request 和 planner evidence 交给执行器；需要明确证明“实际执行的是刚刚通过门禁的计划”，并让组件结果、组合答案、View、Artifact、Evidence 和恢复状态引用同一计划身份。

## 能力模块与依赖

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| execution-binding | 为 validated TaskPlan/DAG 建立有界 execution binding，执行前再次校验计划身份和工具门禁 | M291 TaskPlan completeness、M293 continuation |
| result-closure | 将执行组件、计划步骤、Result/View、事实和限制组合成结构化可读答案与证据 | execution-binding、现有 Result/View/Answer 契约 |
| recovery-parity | 让 binding、结果、答案和 evidence 沿同步/异步、artifact、SQLite/restart 保持一致 | execution-binding、现有 CompositeRun/Async |
| acceptance-harness | 用真实 Domain 数据/回放计划验证规划—执行—答案闭环，保留失败和降级语义 | 前三个模块 |

## 构建顺序

`execution-binding → result-closure → recovery-parity → acceptance-harness → 全局重规划`

本阶段不扩大工具菜单、不增加 RAG、不为单一专题添加流程；最大并发度为 1，任务按完整能力包集中安排，测试按独立失败模式合并执行。
