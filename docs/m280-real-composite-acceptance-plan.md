# Plan: M280 真实跨域 Composite 纵向验收

1. **Response compatibility**：先写 normalizer Spec/contract，支持有限字段别名/默认值；非法字段 fail closed。
2. **Planner evidence**：把 compatibility action、schema status、fingerprint 接入规划响应，保持脱敏。
3. **Offline replay**：用 fake/replay 验证合法计划、repair、provider failure、capability mismatch 和不创建 run。
4. **Live planning**：在 Docker 中显式运行中转 planning probe；按 provider/contract 分层记录，不自动重试昂贵请求。
5. **Real execution**：用合法计划执行 GIS + Economic，比较 sync/async/result/artifact/evidence；必要时再做 orphan restart 验收。
6. **Global review**：更新工作快照、中文问题日志、里程碑并推送；再规划前端动态 Composite View。

## M280 实际收口

- M280-A：新增有界 `normalize_provider_response`，只接受文档化 wrapper/字段别名/安全默认值；未知字段和别名冲突 fail closed，归一化后仍进入现有 canonical Composite contract。
- M280-B：Planning Application 输出脱敏 `planner_evidence`，包含 schema 状态、组件数、fingerprint、planner 来源和 compatibility actions。
- M280-C：Docker 离线 replay **15/15**；显式中转 planning probe 可达但分别出现 `plan_response_field_invalid` 与非 JSON provider response，均安全拒绝且不创建 run。
- M280-D：真实 Docker GIS + Economic 同步、异步 artifact/evidence 和 orphan restart 均通过；restart `recovery_count=1`，组件只执行一次。
- 阶段联合验证：M278 lifecycle/HTTP + M280 acceptance **12/12**，compileall、architecture strict 通过；未改变既有 request/result/lifecycle schema 版本。

下一阶段从全局产品闭环规划动态 Composite View、简洁答案和跨 CLI/HTTP/前端/artifact 的 payload 一致性；provider 输出兼容继续保持显式、有限、可审计，不在 Runtime 或 Domain 中绕过校验。

## 读取范围

- `docs/m280-real-composite-acceptance-spec.md`
- `docs/m280-real-composite-acceptance-plan.md`
- `agent/composite_planner.py`
- `agent/application/composite_planning.py`
- `tests/test_m279_composite_planner.py`
- 后续任务明确列出的 live/evaluation 文件
