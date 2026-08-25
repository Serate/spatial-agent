# M291 Planner 语义完整性与能力计划完整性 Spec

## 目标

建立领域中立的 `spatial-agent.plan-completeness.v1` 校验边界，使 Planner 的“结构合法”与“可执行且语义完整”分离。任何结果进入 execution run 前，都必须证明组件、能力、workflow、工具 allowlist、结果类型和 TaskPlan 之间可以闭合。

## 公共契约

1. `success` 必须包含至少一个组件；组件必须有注册的 `domain_id`、`capability_id`、请求摘要和可物化 workflow。
2. 每个 capability 必须引用已登记 workflow；workflow 的工具集合和结果类型必须覆盖 capability 声明，不能只依赖 Planner 自由补全。
3. component preview 生成的 TaskPlan 必须重新通过 DAG、步数、工具 allowlist、参数 schema 和 result contract 校验。
4. `clarification` 只能表达缺失事实或用户选择；`rejection` 表达能力/权限/契约不允许；`failure` 表达 provider、部署或执行边界失败。
5. 语义不完整的 success 统一映射到有界的 `plan_components_required` 或版本化 completeness reason，不创建 execution run。
6. 语义校验 receipt 只保存状态、reason code、组件数量、能力/工作流摘要和 fingerprint，不保存模型原文。
7. sync、async、artifact、SQLite/restart 和前端 projection 消费同一 completeness receipt，核心状态和证据必须一致。

## 验收

- replay 覆盖合法多组件、success 空组件、未知 workflow、workflow 工具/结果类型不一致、缺失事实和 provider failure。
- capability catalog consistency 检查能定位缺失/不一致声明，并在 planner 或执行前 fail closed。
- TaskPlan bridge 对合法组件仍可接受，对不完整组件不创建 run。
- 前端能将语义拒绝转为简洁中文结论和下一步，不显示内部字段或模型原文。
- Docker 中执行一次合并后的 compact contract、compileall、architecture/readiness 门禁；仅在阶段收口显式执行一次 live probe。

## 阶段实现与验收结果

- 已新增 `spatial-agent.plan-completeness.v1`，并将 catalog consistency、capability binding、TaskPlan materialization 和前端摘要接入公共边界。
- Docker M291 与 M290/M282/M279/M289/M286/M287 合并 **46/46**；组件事实澄清的新增离线回归 **6/6**；Node projection smoke、compileall、architecture strict 和 readiness 200 通过。
- 一次真实 Composite probe：provider structured output 成功、1 次请求、0 重试；Domain preview 返回 `taskplan_component_clarification`，最终无 execution run。该结果已映射为用户可理解的 `NEEDS_CLARIFICATION`，未伪装成成功。
