# M286 中转模型 Planner 适配 Spec

## 目标

在不放宽 Agent Runtime 安全边界的前提下，提高 OpenAI-compatible 中转模型生成合法 Composite 计划的稳定性，并让任何失败都能被用户和开发者区分、恢复和复盘。

## 契约

### 1. 能力身份投影

Planner context 中每个候选能力必须能被模型无歧义复制，至少包含：

```json
{
  "domain_id": "gis",
  "capability_id": "spatial_overview",
  "selection_key": "gis::spatial_overview",
  "tools": ["..."],
  "result_types": ["..."]
}
```

`selection_key` 只是稳定提示，不是新的授权来源；本地仍以 `(domain_id, capability_id)` capability index 和 ToolRegistry 为唯一授权事实。

### 2. Provider 格式适配

provider adapter 可以将文档化的顶层 wrapper、字段别名和有限 outcome 别名转换成 canonical planner payload。每个兼容动作必须可记录为字段名/动作名摘要。

以下情况必须拒绝：未知字段、冲突别名、非对象顶层、非数组 components、非成功 outcome 携带 components、成功 outcome 没有 components、无法解析的 JSON 和超过预算的响应。

其中 `components` 超过 8 项必须返回有界错误，不能静默截断后执行；截断只允许用于模型上下文的展示预算，不允许用于可执行计划。

### 3. Planner 失败分类

统一使用有限错误码，至少区分：

- `planner_provider_failed`
- `plan_response_field_invalid`
- `plan_components_unexpected`
- `capability_not_registered`
- `capability_unavailable`
- `taskplan_policy_unavailable`
- `plan_*` schema/字段错误

失败不得创建 execution run；planner evidence 只能保存安全状态、错误码、候选数量、选择来源、fingerprint、修复次数、步骤数，以及有界的 `domain_id::capability_id` 选择键，不保存参数值或模型原文。

### 4. 入口一致性

同一拒绝结果经 direct application、HTTP planning、async submit、artifact/detail/restart 和 Console projection 时，核心状态、错误码、planner source、组件数和证据 fingerprint 一致。前端不得按 provider 名称或具体 Domain 分支渲染。

## 阶段任务包

1. 收敛 context 的能力身份投影和预算，增加脱敏字段契约。
2. 收敛 provider response normalizer 的文档化兼容范围和冲突拒绝。
3. 收敛 Planner application 的错误分类、有限 repair lineage 和 TaskPlan policy 反馈。
4. 接入 HTTP/async/artifact/restart/frontend 的通用失败 projection，保持成功路径不变。
5. 增加少量独立 replay/contract 场景，执行一次 Docker 阶段门禁和一次显式 live probe。
6. 更新中文问题日志、milestones、任务账本和部署说明，完成提交推送并全局重规划。

## 验收

- 一个脱敏 replay 能生成至少两步、带依赖且身份精确的合法计划。
- 字段漂移、非成功组件、未知能力、不可用能力和 TaskPlan policy 失败均在执行前安全拒绝。
- 同一失败经过 HTTP/async/artifact/restart/前端 projection 保持核心事实一致。
- Docker compileall、architecture strict、readiness 和精简 M286 contract 通过。
- 真实中转单次 probe 只记录脱敏 receipt；若仍失败，结果必须明确归类，不能伪装成成功。
