# Spec：M323 人工审批、持久化和 Registry 治理

## Objective

为 M322 的 `tool-proposal-receipt.v1` 增加显式人工审批和可恢复治理。用户或管理员能够查看
有界提案摘要，批准、拒绝、撤销或让提案过期；只有批准且版本匹配的提案才能进入 ToolRegistry。

## 公共契约

- `spatial-agent.tool-approval.v1`：proposal identity、receipt hash、状态、版本、决策者标识摘要、
  时间和过期时间；不包含源码、示例参数、Prompt、模型原文或密钥。
- 状态：`pending`、`approved`、`rejected`、`expired`、`revoked`、`invalid`。
- 决策必须带 `expected_version` 或 receipt fingerprint；重复同一决策幂等，过期版本 fail closed。
- 批准后只发布 Registry definition 和受控 handler 引用；不能直接从 HTTP 参数加载源码。

## 生命周期

```text
validated receipt → pending → approved → registered
                           ↘ rejected
                           ↘ expired
approved/registered → revoked
invalid receipt → invalid
```

所有状态转换产生有界 decision receipt，并可通过 SQLite 重启恢复。`pending`、`rejected`、
`expired`、`revoked` 和 `invalid` 不能被 Runtime dispatch。

## HTTP/CLI 边界

- 查询提案列表和单个提案摘要。
- 提交批准、拒绝、撤销决策；请求必须包含提案 ID、版本和决策动作。
- 决策冲突、未知提案、receipt 不匹配、过期和未授权都返回结构化错误。
- 传输层只解析 URL/JSON，语义分发继续由共享 `HTTPApplication` 完成。

## Testing Strategy

- 紧凑契约：状态矩阵、幂等、版本冲突、不可执行 gate、脱敏和 Registry 隔离。
- Docker：SQLite 重启恢复、HTTP contract、approved/revoked 执行边界。
- 阶段收口：compileall、architecture strict、readiness 和一条跨入口验收；不调用真实模型。

## Boundaries

- Always：所有决策校验 receipt fingerprint、版本、权限和状态；所有工具继续通过 ToolRegistry。
- Ask first：改变审批角色模型、持久化 schema 或发布策略时更新 Spec。
- Never：自动批准、主进程执行未批准源码、绕过 Registry、保存源码全文或敏感模型数据。

## Success Criteria

1. M322 validated receipt 能稳定进入 pending，并跨 SQLite 重启恢复。
2. 只有显式 approved 且版本匹配的提案才进入 Registry。
3. rejected、expired、revoked 和冲突决策不能执行，且返回可读 evidence。
4. CLI、HTTP、运行时和恢复流程对同一提案保持 identity 一致。
5. 所有公开投影不包含源码、示例参数、Prompt、模型原文或密钥。

## Open Questions

- 首版使用单一受控管理员角色摘要，不引入完整账号/组织权限系统；后续如需多角色再扩展契约。
