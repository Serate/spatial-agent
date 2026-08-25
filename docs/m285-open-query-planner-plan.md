# Plan: M285 开放式 Planner 多工具编排纵向切片

## 实施顺序

1. **A 全局规划**：✅ 完成 capability map、Spec、Plan；明确复用 M282/M283/M284 的 context、planner、reset 和 projection 契约。
2. **B Planner entry policy**：整理 Rule/Replay/LLM 的选择原因和统一 planner source evidence；不改变 Runtime 生命周期。
3. **C TaskPlan bridge**：将开放式候选归一为既有 `TaskPlan`/DAG，集中执行 schema、workflow、allowlist 和结果类型门控；补一个至少两步的 replay fixture。✅ 已实现 `CompositeTaskPlanBridge`，并接入 planner evidence。
4. **D 跨入口验收**：用精简 Python/HTTP/async/artifact 契约验证成功、澄清、拒绝和 provider failure；只在需要时补前端 plan/evidence 投影断言。
5. **E 显式 live 与收口**：Docker 重建后执行真实模型 + local GIS 单 case，更新中文问题日志、milestones、恢复账本、任务清单，提交推送并全局重规划。

## 文件边界

- B/C：优先修改已有 Planner gateway/application seam 和 `tests/test_m285_open_query_planner.py`；不修改 GIS/Economic 业务算法。
- D：只修改必要的 HTTP/async/artifact contract 测试和通用前端 projection 文件。
- E：`docs/agent-development-issues.md`、`docs/milestones.md`、`tasks/*`、`docs/agent-work-state.md`。

## 风险与控制

- Planner 输出字段漂移：复用现有 normalizer，未知字段 fail closed；replay 先行。
- “开放式”退化成关键词匹配：验收请求不绑定固定问句，测试断言 selected capability 与 DAG 结构，不断言关键词分支。
- 测试膨胀：只保留成功/澄清/拒绝/provider failure 四种独立失败模式，加一条 HTTP/async/artifact 入口验收。
- 真实 provider 不稳定：live 单独执行并记录安全 receipt，不把网络失败混入离线 CI。
- 架构回退：architecture strict 检查公共 Runtime 不引用 GIS/Economic 专用策略；不新增前端领域分支。

## Verification Checkpoints

- B：planner source/selection evidence contract。
- C：至少两步 TaskPlan replay 成功 + 非法工具/结果类型在执行前 fail closed。✅ 已覆盖两步依赖和非法工具。
- D：Docker 定向契约、compileall、architecture strict、readiness 和跨入口核心结果一致。
- E：显式 live receipt、中文记录、版本推送和全局重规划。
