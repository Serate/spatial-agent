# M280 当前实施计划

本阶段依据 [`docs/m280-real-composite-acceptance-capability-map.md`](../docs/m280-real-composite-acceptance-capability-map.md)、[`docs/m280-real-composite-acceptance-spec.md`](../docs/m280-real-composite-acceptance-spec.md) 和 [`docs/m280-real-composite-acceptance-plan.md`](../docs/m280-real-composite-acceptance-plan.md) 执行。

当前恢复快照：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前阶段规划和快照列出的文件。M279 已完成并推送，M280 准备开始实现。

1. Response compatibility：有限字段兼容与 fail-closed。
2. Planner evidence：compatibility/status/fingerprint 摘要。
3. 离线 replay 与显式 live planning probe。
4. 真实 GIS + Economic sync/async/restart/evidence 验收。
5. Docker 验收、中文记录、提交推送和全局重规划。
