# M285 能力图：开放式 Planner 多工具编排纵向切片

## 目标

把现有的能力目录、Planner 和 Runtime 连接成一条可证明的开放式成功路径：用户提出未被固定问句覆盖的问题时，Planner 从受信任的 Domain catalog/context 中选择已注册能力，生成可校验的 canonical TaskPlan/DAG，再交给既有 Runtime 执行、组合结果并展示证据。

本阶段解决“架构已有，但默认成功路径仍像查询引擎”的系统性缺口；不围绕洪山区、某个指标或某一种表达增加规则分支。

## 模块与依赖

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| planner-entry-policy | 区分开放式 Planner、规则兜底和回放验收入口，记录选择原因 | `RequestFacts`、Domain catalog |
| taskplan-bridge | 将 Rule/Replay/LLM 的候选统一归一为版本化 TaskPlan/DAG，执行前完成 allowlist/schema 门控 | planner-entry-policy、现有 `TaskPlan`/workflow |
| open-query-acceptance | 用脱敏 replay fixture 验证至少两步工具组合、澄清、拒绝和 provider 失败 | taskplan-bridge、Runtime lifecycle |
| cross-entry-plan-evidence | 让 plan source、selected capabilities、校验结果和 repair lineage 在同步/异步/artifact/前端保持一致 | taskplan-bridge、Result/Evidence |

## 构建顺序

`planner-entry-policy` → `taskplan-bridge` → `open-query-acceptance` → `cross-entry-plan-evidence` → 显式 live 验收与全局重规划。

## 边界

- 公共 Runtime、ToolRegistry、Result schema 和 Domain Pack 的现有工具实现继续作为执行边界。
- LLM 只能选择 context/catalog 中的能力；不能发明工具、数据、路径、测量或代码。
- Replay 只保存脱敏 alias 与结构化输出，不保存 prompt、模型原文、密钥或私有路径。
- 规则 Planner 是离线确定性兜底；它与 LLM/Replay 必须产出同一 TaskPlan 契约。
- GIS 和经济数据只作为显式验收载体，不进入公共规划策略。
