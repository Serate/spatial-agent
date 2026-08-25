# Spec: M285 开放式 Planner 多工具编排纵向切片

## Objective

面向希望用自然语言完成空间/多领域分析的用户，建立一条真实可观测的开放式 Planner 成功路径。Planner 应从已注册能力和有界请求上下文中自主选择多个能力，并把结果交给现有 Agent Runtime；用户可以看到“能力选择 → 计划校验 → 工具执行 → 结果/证据”的结构化摘要，而不是只看到一个固定查询结果。

### 假设

1. 现有 `TaskPlan`、workflow、ToolRegistry、Runtime lifecycle、Result/View/Evidence 和跨入口应用边界继续有效。
2. 本阶段不引入 RAG、外部搜索、新 GIS/经济数据或新的第三方依赖。
3. 默认自动化验收离线且精简；真实模型 + local GIS/Docker 只作为显式验收路径。
4. Goal 当前按串行方式执行；每个子任务先写入 `tasks/task-progress.md`。

## Commands

```text
Docker build: docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build spatial-agent
Contract: docker exec ai-agent-spatial-agent-1 /opt/conda/envs/spatial-agent-gis/bin/python -m unittest tests.test_m285_open_query_planner -v
Compile: docker exec ai-agent-spatial-agent-1 /opt/conda/envs/spatial-agent-gis/bin/python -m compileall -q agent domains production_api.py serve_api.py
Architecture: docker exec ai-agent-spatial-agent-1 /opt/conda/envs/spatial-agent-gis/bin/python scripts/architecture_check.py --strict
Readiness: Invoke-WebRequest -Uri http://127.0.0.1:8088/health/ready -UseBasicParsing
Frontend regression: node scripts/console_result_projection_smoke.js
Explicit live path: SPATIAL_AGENT_LIVE_OPENAI=1 python scripts/evaluation_live.py --case <documented-case>
```

## Project Structure

```text
agent/                         → Planner/TaskPlan/Runtime 公共边界
agent/composite_planner.py     → 现有 Composite provider normalization，按需复用
agent/runtime_core/            → 计划校验、执行和生命周期 seam
domains/*/                     → Domain catalog、workflow、工具和结果实现
tests/test_m285_open_query_planner.py → 精简 replay/TaskPlan/门控契约
docs/m285-open-query-planner-*.md    → capability map、Spec、Plan
tasks/task-progress.md         → 当前子任务与恢复指针
```

## Contract

每个 Planner 入口都必须返回或安全终止于同一结构化结果：

```python
{
    "planner_source": "rule|replay|llm",
    "plan": {"goal": "...", "steps": [{"id": "...", "tool": "registered", "args": {}, "depends_on": []}]},
    "plan_evidence": {"selected_capabilities": ["..."], "validation": "accepted|rejected|clarification"},
}
```

实际公共 schema 以现有版本化契约为准；示例不允许绕过 `TaskPlan` parser、workflow validator 或 ToolRegistry。

开放式 Composite 候选通过 `task_plan_bridge` 进入该门控。脱敏 replay 可在
`component.workflow.task_plan` 中提供 `goal/steps/output/assumptions`；桥接只向
结果和 evidence 暴露步骤、依赖、工具名、参数键和结果类型，不保存参数值。没有
显式 replay 计划时，若 Domain Service 提供 planning-only `preview()`，则复用其
TaskPlan；旧候选暂时返回 `deferred`，不得把未校验候选直接提交为可执行 run。

## Code Style

公共 seam 使用小的纯函数和显式依赖，避免在 Runtime 中按领域/区域判断：

```python
def accept_candidate(candidate, *, context, allowlist):
    plan = normalize_candidate(candidate, context=context)
    validate_plan(plan, allowlist=allowlist)
    return plan
```

函数名表达边界动作；错误使用有限 machine-readable code；不得把模型原文或敏感配置写入 evidence。

## Testing Strategy

- Contract：一个多步 replay 成功、一个澄清、一个非法能力/字段拒绝、一个 provider failure；断言最终状态、TaskPlan、allowlist、evidence 和无越权执行。
- Integration：Docker 内 compileall、architecture strict、readiness 和一条 HTTP/async/artifact 结果一致性验收。
- Browser：复用现有 projection smoke，仅在结构化 plan/evidence 改变用户投影时增加一个断言，不复制地图或领域页面分支。
- Live：显式执行一条真实模型 + local GIS case，只记录状态、步骤数、延迟/token 摘要；不进入默认 CI。

## Boundaries

- Always：所有模型候选先做 schema、能力 allowlist、workflow 和数据可用性校验；所有子任务先更新任务账本；失败要保留安全 evidence。
- Ask first：修改公共 Result schema、数据库 schema、HTTP 语义、引入第三方依赖、改变默认 provider 或加入外部数据源。
- Never：为固定问句/区域/工具名增加专用分支；绕过 ToolRegistry；放宽未知模型字段；提交 key、prompt、模型原文或私有路径；删除失败测试。

## Success Criteria

1. 一个没有固定模板命中的开放式 replay 请求能生成至少两步、带依赖的 canonical TaskPlan，并通过同一 Runtime 执行门控；结果保留 `task_plan_bridge` 的结构化 DAG 证据。
2. Rule、Replay、LLM 三种入口在相同 context 下共享 plan parser、allowlist、校验和证据结构；非法工具/字段在执行前拒绝。
3. 成功、澄清、拒绝、provider failure 都返回结构化终态，不创建越权 run；repair lineage（若存在）可读且有界。
4. 同步、异步、artifact/detail 和前端对 plan source、步骤数、结果状态的核心事实一致。
5. Docker compileall、architecture strict、readiness、精简契约与显式 live 验收通过；默认 CI 不依赖模型或私有数据。

## Open Questions

- 后续是否把多 Domain 组件计划与单 Domain TaskPlan 合并为一个更高层 workflow contract？M285 只建立桥接证据，不修改公共 schema 版本。
