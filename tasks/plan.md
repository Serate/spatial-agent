# M287 当前实施计划

本阶段依据 [`docs/m287-bounded-planner-repair-capability-map.md`](../docs/m287-bounded-planner-repair-capability-map.md)、[`docs/m287-bounded-planner-repair-spec.md`](../docs/m287-bounded-planner-repair-spec.md) 和 [`docs/m287-bounded-planner-repair-plan.md`](../docs/m287-bounded-planner-repair-plan.md) 执行。

当前恢复快照：[`docs/agent-work-state.md`](../docs/agent-work-state.md)。恢复时只读取当前阶段规划、任务进度账本最近记录和快照列出的文件。M286 已完成本阶段验收并待本轮版本交付，M287-A 已完成，当前进入 M287-B；阶段按完整能力切片集中实现，减少重复测试。

1. [x] M287-A 完成七维度能力图、Spec、Plan。
2. [ ] M287-B 建立 Repair Request/Lineage contract 和错误码白名单。
3. [ ] M287-C 接入 provider/application 一次性修复回合。
4. [ ] M287-D 完成跨入口恢复与前端阶段投影。
5. [ ] M287-E 集中 Docker/live 验收、中文记录、提交推送和全局重规划。
