# Plan: M282 开放式请求解析与受控 Composite Planner

## 实施顺序

1. **A Context contract**：✅ 新增 `composite-request-context.v2` builder，聚合 Domain RequestFacts/discovery/catalog，执行字段、数量和字节预算。
2. **B Capability matching**：✅ 把候选能力、workflow、data readiness 和缺失事实投影给 Planner；候选不明确时不求并集，不可用能力输出结构化 clarification。
3. **C Planner gateway**：✅ Rule/LLM Composite Planner 使用同一 context contract；保留 canonical normalize、allowlist、有限 repair 和 planner evidence。
4. **D Cross-entry acceptance**：✅ HTTPApplication、FastAPI/stdlib semantic route、异步生命周期回归复用同一 context/plan/clarification/evidence 边界。
5. **E 收口与全局重规划**：进行中；完成 Docker/readiness/live 短验收、中文记录、提交推送后从七维度规划下一阶段。

## 风险与缓解

- Domain facts 形状不一致：只调用既有 `as_context_dict/as_dict`，统一 safe projection，保留 domain_id 和 schema。
- context 过大：每个 Domain、候选和 evidence 独立预算；超限返回 `context_budget_exceeded`，不截断成误导性成功。
- Rule Planner 过于保守：先将“保守澄清”作为明确产品状态，不偷偷增加关键词分支；用 fake/真实 probe 衡量再决定是否扩展 catalog 声明。
- Provider 输出不稳定：canonical schema 和 local allowlist 仍是唯一门禁，provider failure 只生成结构化 receipt。
- 跨入口漂移：所有入口只调用 `CompositePlanningApplication`/`HTTPApplication`，用 fingerprint 和公共状态做比较。

## Verification Checkpoints

- A 后：context fake contract 和 `git diff --check`。
- B 后：多 Domain candidate/clarification contract，未知能力无 execution。
- C 后：M279 Planner 回归与 planner evidence fingerprint。
- D 后：FastAPI/stdlib/async semantic contract；Docker 重建后再执行。
- E 后：阶段记录、推送版本和全局重规划完成。

## 当前验收记录

- Docker 重建后 M282/M279/M281 定向回归 **24/24**；M278 Composite 生命周期/HTTP **7/7**；compileall、architecture strict 通过。
- 真实 Docker production `/health/ready` 返回 HTTP 200；本地 GIS、live LLM 配置和网络能力均由容器报告可用。Rule `/composite-plans` 返回 v2 context 与结构化澄清，不创建 run。
- 显式真实模型短探测到达 provider 并返回 HTTP 200，但模型输出不符合 Composite Planner 字段 allowlist，系统返回 `REJECTED/plan_response_field_invalid`、0 个组件、无 run；未输出或保存模型原文。
