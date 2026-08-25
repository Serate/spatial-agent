# M287 有界 Planner 修复与失败恢复 Spec

## Objective

对有限的 Planner schema 错误提供一次可观测、可取消、可恢复的修复机会；修复结果必须重新通过现有 Planner normalization、capability allowlist、TaskPlan bridge 和 Runtime 执行门控。

## Repair Request

```json
{
  "schema_version": "spatial-agent.planner-repair-request.v1",
  "reason_code": "plan_component_field_invalid",
  "request_fingerprint": "...",
  "context_schema_version": "...",
  "allowed_outcome": "success|needs_clarification|rejected",
  "attempt": 1,
  "max_attempts": 1
}
```

只允许有限 `reason_code`：`plan_response_field_invalid`、`plan_component_field_invalid`、`plan_components_unexpected`、`plan_components_invalid`、`plan_component_field_missing`。`capability_not_registered`、`capability_unavailable`、数据/权限/TaskPlan policy 失败不得通过模型修复。

## Repair Lineage

```json
{
  "schema_version": "spatial-agent.planner-repair-lineage.v1",
  "attempted": true,
  "count": 1,
  "reason_code": "...",
  "status": "not_attempted|repaired|failed|skipped",
  "request_fingerprint": "..."
}
```

不得记录原始 provider response、未知字段名、完整 prompt 或修复文本；修复成功后仍只保存 canonical plan 与安全结构投影。

## 生命周期与入口

- `resolve → clarify → plan → validate → repair(最多一次) → validate → execute → answer → evidence`。
- repair 使用同一个请求 fingerprint、context snapshot、deadline 和幂等边界；不得创建第二个 execution run。
- HTTP、async、artifact、SQLite/restart 和前端只消费统一 Planner evidence/lineage。
- repair 超时、provider 失败或再次非法时返回原始安全错误的结构化失败，不吞掉或伪装成功。

## 验收标准

1. replay 的 schema 错误可修复为合法两步 TaskPlan，并记录一次 lineage。
2. 修复再次失败时无 run 或只有一个受控 run，状态、错误码和 lineage 一致。
3. 未知 capability、不可用数据、非法工具和 policy 失败不触发 repair。
4. Docker contract、compileall、architecture strict、readiness 通过；真实中转只做一次显式验收。
