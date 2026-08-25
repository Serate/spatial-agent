# Spec: M294 已验证计划到执行/答案/证据闭合

## Objective

让系统从已验证的 Composite TaskPlan/DAG 开始执行同一份计划，而不是只把计划摘要作为 evidence 再次按请求猜测。每个组件的工具步骤、依赖、Result 类型、事实来源、答案和 evidence 必须可追溯到同一 `plan_fingerprint`；同步、异步、artifact、SQLite/restart 和前端展示的核心结果保持一致。

## Public contract

1. 新增版本化 `spatial-agent.execution-binding.v1`，至少包含 request fingerprint、plan fingerprint、component IDs、每个组件的 bounded TaskPlan/DAG、允许工具、结果类型和 binding state。
2. binding 只能由已经通过 capability allowlist、workflow binding、TaskPlan schema、DAG 和 completeness gate 的计划生成；执行入口拒绝缺少 binding、binding 指纹不一致或工具/结果类型漂移。
3. Composite coordinator/Domain executor 接收 binding 作为受校验的执行输入；不得从用户原文或模型原文重新推断步骤。Runtime、ToolRegistry 和生命周期状态机保持公共复用。
4. 组件结果保留 component ID、plan step ID、result type、数据形态、来源 evidence 和错误/降级状态；组合 Result/View/Artifact/Evidence 使用同一 binding identity。
5. 答案生成只消费结构化结果、限制、证据和用户请求摘要；模型不可用或回答 schema 不合格时使用结构化 fallback，但不得改变结果事实、状态或 plan fingerprint。
6. 同步/异步、artifact、SQLite/restart 和前端对同一 binding 返回一致的核心结果；失败时保留可读的 binding/repair/recovery lineage，不把部分完成伪装为原计划完成。

## Commands

- 构建镜像：`docker compose -f docker-compose.prod.yml build spatial-agent`
- 阶段契约：`docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m294_execution_binding_closure -v`
- 统一门禁：`docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains evaluation production_api.py serve_api.py`
- 架构门禁：`docker exec ai-agent-spatial-agent-1 python scripts/architecture_check.py --strict`
- readiness：`Invoke-WebRequest -Uri http://127.0.0.1:8088/health/ready -UseBasicParsing`

## Project structure

- `agent/runtime_core/`：binding、TaskPlan/DAG 和执行前门禁。
- `agent/application/`：Planner prepare/submit、CompositeRun 和跨入口生命周期。
- `agent/application/composite.py` 或对应 coordinator：消费 validated binding 并关联组件结果。
- `agent/composite_view.py`、`agent/answer_generation.py`、`web/src/console_result_projection.js`：结果/答案/证据投影。
- `tests/test_m294_execution_binding_closure.py`：一个 compact contract 模块。

## Code style

继续使用领域中立的、版本化的结构化边界，binding 不携带 prompt、模型原文、凭据或私有路径：

```python
return {
    "schema_version": "spatial-agent.execution-binding.v1",
    "plan_fingerprint": plan_fingerprint,
    "components": bounded_components,
    "state": "validated",
}
```

执行器只接受 binding 中已校验的工具和参数引用；错误通过稳定 code 和 lineage 返回，不能通过字符串匹配恢复。

## Testing strategy

- 默认增加一个 M294 compact contract，集中覆盖 binding 成功、计划/工具/结果漂移拒绝、同步/异步 evidence 一致和结果/答案 fallback。
- 实现集中完成后统一运行该模块、M293/M291 相邻回归、compileall、architecture strict、readiness；不为每个 adapter 或页面改动单独增加测试轮次。
- 真实 GIS/数据和真实模型只做显式端到端验收，优先使用已经准备好的 Docker 数据；失败分类必须区分 Planner、binding、ToolRegistry、Domain 数据和答案生成。

## Boundaries

- Always：执行前验证 binding；结果引用 plan/component/step；保留 evidence 和降级边界。
- Ask first：改变现有 Result/Artifact schema 版本、引入新的执行队列或替换 Domain coordinator。
- Never：以 planner evidence 代替执行输入；重新从固定问句猜步骤；为了 live 通过放宽工具 allowlist、TaskPlan 或答案事实校验。

## Success criteria

1. 一个合法多组件计划在同步和异步路径实际执行同一份 binding，并能从结果追溯到 component/step/plan fingerprint。
2. binding 被篡改、计划漂移、工具未注册或结果类型不匹配时，在创建 run/dispatch 前结构化拒绝。
3. artifact、SQLite/restart、View、Evidence 和前端显示与同步核心结果一致。
4. 结构化答案优先使用真实工具事实；答案生成失败时 fallback 可读且不改变事实与状态。
5. 默认测试保持精简，至少一条 Docker 真实数据或回放计划的跨入口验收证明闭合链路。

## Open questions

- 是否允许一个组件包含多个独立 TaskPlan：本阶段仍使用一个组件一个 bounded TaskPlan，避免扩大 binding schema；未来若需要再单独规划。
