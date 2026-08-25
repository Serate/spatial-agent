# 当前任务状态账本

> 这是恢复上下文时使用的短任务账本，不是完整历史日志。
> 每次开始、完成或暂停一个子任务都要更新对应记录；阶段收口后，把完整结论归档到阶段 Spec/Plan 或里程碑文档，本文件只保留当前阶段和最近记录。

## 当前阶段

- 阶段：M280 真实跨域 Composite 纵向验收
- 阶段规划：
  - `docs/m280-real-composite-acceptance-capability-map.md`
  - `docs/m280-real-composite-acceptance-spec.md`
  - `docs/m280-real-composite-acceptance-plan.md`
- 执行方式：串行；默认测试离线精简；真实模型、GIS、Docker 只做显式验收

## 任务记录

### CONTEXT-001：最小恢复上下文（已完成）

- 目标：让新对话只恢复当前阶段规划、最近任务和明确待修改文件。
- 改动：新增本账本；精简 `docs/agent-work-state.md`；恢复脚本默认只读取快照与本账本；项目 Goal 增加恢复约束。
- 验证：`pwsh -NoProfile -File scripts/resume_context.ps1` 退出码 0；`git diff --check` 通过。
- 阻塞：无。
- 下一步：继续 M280-A；恢复时只读取 M280 规划和其明确文件。

### M280-A：Planner response compatibility（待开始）

- 目标：对真实中转模型的有限别名/省略字段做有界归一化，最终仍经过现有 canonical plan contract；未知字段必须拒绝。
- 待读/待修改：
  - `agent/composite_planner.py`
  - `agent/application/composite_planning.py`
  - `tests/test_m280_real_composite_acceptance.py`（新增）
- 验证：Docker 离线 replay/fake 测试；不调用网络、不保存模型原文。
- 阻塞：无。
- 下一步：先阅读 M280 Spec/Plan 和上述三个文件，补红测，再实现 normalizer。

## 更新协议

1. 开始子任务：写入“进行中”、目标、明确文件和验证方式。
2. 完成子任务：补充实际改动、验证结果、阻塞和下一步。
3. 暂停或阻塞：保留可复现的阻塞原因和恢复条件，不把未知问题写成已完成。
4. 阶段完成：更新本账本、`docs/agent-work-state.md`、阶段文档和 `tasks/todo.md`，再提交推送并进行全局重规划。
