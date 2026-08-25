# M285 当前实施计划

本阶段依据 [`docs/m285-open-query-planner-capability-map.md`](../docs/m285-open-query-planner-capability-map.md)、[`docs/m285-open-query-planner-spec.md`](../docs/m285-open-query-planner-spec.md) 和 [`docs/m285-open-query-planner-plan.md`](../docs/m285-open-query-planner-plan.md) 执行。

当前恢复快照：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前阶段规划、任务进度账本最近记录和快照列出的文件。M284 已完成并推送，M285-A/B 已完成，当前进入 M285-C TaskPlan bridge。

1. [x] M285-A 完成全局 capability map、Spec、Plan。
2. [x] M285-B 收口 Planner entry policy 与 source evidence。
3. [x] M285-C 建立至少两步 TaskPlan replay bridge 与执行前门控。
4. [x] M285-D 完成 Python/HTTP/async/artifact 精简跨入口验收。
5. [ ] M285-E 完成 Docker/live/中文记录、提交推送和全局重规划（live provider 仍有结构化输出阻塞）。
