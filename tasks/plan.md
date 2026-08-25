# M282 当前实施计划

本阶段依据 [`docs/m282-open-query-resolution-capability-map.md`](../docs/m282-open-query-resolution-capability-map.md)、[`docs/m282-open-query-resolution-spec.md`](../docs/m282-open-query-resolution-spec.md) 和 [`docs/m282-open-query-resolution-plan.md`](../docs/m282-open-query-resolution-plan.md) 执行。

当前恢复快照：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前阶段规划、任务进度账本最近记录和快照列出的文件。M281 已完成并推送，M282-A/B/C/D 已完成，当前进入阶段验收与版本交付。

1. [x] Domain RequestFacts/discovery/catalog 聚合为公共 `composite-request-context.v2`。
2. [x] 候选能力、缺失事实、数据就绪和澄清状态统一投影并收口。
3. [x] Rule/LLM Planner 共享 context、canonical plan 和有限 repair 门禁。
4. [x] CLI/HTTP/stdlib/async 的开放请求结果一致，未知能力不创建 run。
5. [ ] Docker/真实数据/模型/browser 显式验收、中文记录、提交推送和全局重规划。
