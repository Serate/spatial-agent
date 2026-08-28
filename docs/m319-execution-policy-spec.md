# Spec：M319 通用 Execution Policy 接入

## Objective

让现有 Runtime 能在没有 workflow 的情况下安全执行普通单工具计划和通用 DAG，同时
把 Domain workflow、未来 ReAct、动作预算、结果类型和确认要求投影为同一个版本化
`spatial-agent.execution-policy.v1`。用户不需要为每个新能力先创建固定 workflow；高风险
Domain 仍可在自己的 seam 中拒绝不满足条件的计划。

## Commands

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m319_execution_policy -v
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m compileall -q agent domains scripts
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/architecture_check.py --strict
```

## Project Structure

- `agent/runtime_core/execution_policy.py`：策略契约、解析和计划门禁。
- `agent/runtime_core/planning_surface.py`：规划后的统一验证入口。
- `agent/runtime_core/run_lifecycle.py`：同步生命周期不再无条件要求 workflow。
- `agent/runtime_core/preview.py`：预览与真实执行消费相同策略证据。
- `agent/runtime.py`：策略配置、治理兼容投影和重规划刷新。
- `tests/test_m319_execution_policy.py`：精简策略矩阵和 Runtime 接入契约。

## Code Style

策略解析返回 JSON-safe 的字典；解析器不调用工具，不读取模型原文，不把 Domain
标识写入公共 Runtime 分支。计划门禁使用稳定错误码：

```python
policy = resolver.resolve(plan, workflow=workflow, domain_policy=domain_policy)
resolver.validate_plan(plan, policy)
```

## Testing Strategy

- 直接覆盖四种策略的解析和工具/结果/动作预算失败。
- 覆盖无 workflow 的普通计划可以通过，显式 workflow 仍走 Domain validator。
- 覆盖 Runtime 结果中的 policy evidence 与预览结果中的 policy evidence 使用同一契约。
- Docker 阶段收口再运行 compileall 和 architecture strict；不调用真实模型。

## Boundaries

- Always：先执行 Domain 校验和通用 TaskPlan/DAG 校验；策略只允许已登记工具和有限结果类型。
- Ask first：改变公开策略 schema、默认预算或 CI 配置。
- Never：用策略解析绕过权限、数据 readiness、workflow 高风险校验或 ToolRegistry。

## Success Criteria

1. direct tool、generated DAG、Domain workflow 和显式 ReAct 都能生成合法 policy。
2. 无 workflow 的普通计划不因缺少 workflow 被阻断。
3. 未登记工具、超出动作预算、未允许结果类型的计划 fail closed。
4. 同步、preview、replan 和持久化结果保留相同的 policy 核心字段及旧治理摘要。
5. 旧 execution-binding 和默认 Domain 行为不发生不必要的 schema 漂移。

## Open Questions

M320 决定 ReAct planner 如何把 `requested_mode="react"` 传给解析器；M319 只提供稳定
策略 seam，不伪造 ReAct 轮次。
