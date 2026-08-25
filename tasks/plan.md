# M279 当前实施计划

本阶段依据 [`docs/m279-composite-planner-capability-map.md`](../docs/m279-composite-planner-capability-map.md)、[`docs/m279-composite-planner-spec.md`](../docs/m279-composite-planner-spec.md) 和 [`docs/m279-composite-planner-plan.md`](../docs/m279-composite-planner-plan.md) 执行。

当前恢复快照：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前阶段规划和快照列出的文件。本阶段 M278 已完成并推送，M279 准备开始实现。

1. Catalog projection：生成领域中立、有界的 Planner context。
2. Rule/LLM Composite Planner：输出同一 canonical request 并通过校验。
3. CompositePlanningApplication：resolve、plan、validate/repair、clarify、submit。
4. HTTP/CLI semantic command 与跨入口一致性。
5. Docker 验收、中文记录、提交推送和全局重规划。
