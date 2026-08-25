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

### M280-A：Planner response compatibility（进行中）

- 目标：对真实中转模型的有限别名/省略字段做有界归一化，最终仍经过现有 canonical plan contract；未知字段必须拒绝。
- 改动：新增独立 `normalize_provider_response`；支持 `plan/status/objective/steps` 等文档化字段映射、组件别名和有限默认值；未知字段/别名冲突 fail closed；新增离线 replay 契约测试。
- 改动文件：
  - `agent/composite_planner.py`
  - `tests/test_m280_real_composite_acceptance.py`
- 验证：Docker `tests.test_m280_real_composite_acceptance tests.test_m279_composite_planner` **13/13**；Docker compileall 通过；不调用网络、不保存模型原文。
- 阻塞：无。
- 下一步：M280-A 已完成，进入 M280-B Planner evidence。

### M280-B：Planner evidence（已完成）

- 目标：把 compatibility action、schema status、component count 和 canonical fingerprint 作为脱敏 planner evidence 返回；不改变 Composite request/result/lifecycle schema。
- 待读/待修改：
  - `agent/application/composite_planning.py`
  - `tests/test_m280_real_composite_acceptance.py`
- 验证：Docker `tests.test_m280_real_composite_acceptance tests.test_m279_composite_planner` **14/14**；compileall 通过；确认不含 prompt、模型原文、密钥或私有路径。
- 阻塞：无。
- 下一步：进入 M280-C 离线 replay 与显式 live planning probe。

### M280-C：Planning probe（已完成）

- 目标：复用现有 provider probe/harness 记录一次脱敏 Composite planning 结果；离线 replay 覆盖成功、澄清、拒绝和 provider failure；真实请求只显式运行，不进入默认 CI。
- 待读/待修改：
  - `evaluation/live_provider_probe.py`
  - `scripts/live_provider_probe.py`
  - `production_api.py`（仅读取 Planner composition seam）
  - `agent/composite_planner.py`（仅按安全字段形状修正兼容面）
  - `tests/test_m280_real_composite_acceptance.py`
- 验证：Docker 离线回归 **15/15**；真实 planning probe 到达中转并返回脱敏 `REJECTED/plan_response_field_invalid`，另一次安全形状诊断返回非 JSON；均未创建 execution run，不保存 prompt、模型原文、密钥或私有路径。
- 阻塞：provider 当前不能稳定产出 Composite canonical JSON；按 Spec 保留失败 receipt，不盲目扩大兼容面。
- 下一步：进入 M280-D，用合法 canonical plan 验证真实 GIS + Economic 执行和恢复边界。

### M280-D：真实跨域执行与恢复（已完成）

- 目标：在 Docker 真实数据上执行合法 GIS + Economic Composite，比较 sync/async/artifact/evidence，并验证 orphan restart 只接管一次。
- 待读/待修改：
  - `agent/application/composite_runs.py`
  - `agent/application/composite.py`
  - `scripts/m280_real_composite_acceptance.py`（新增，显式 Docker 验收）
  - `tests/test_m278_composite_lifecycle.py`
  - `tests/test_m278_composite_http.py`
  - `tests/test_m280_real_composite_acceptance.py`
- 验证：Docker 真实同步 GIS + Economic 为 `COMPLETED/composite_result`；真实 async 的 artifact、observability、evidence 均可用；真实 orphan restart `recovered=true`、`recovery_count=1`，两个组件均完成；M278 lifecycle/HTTP + M280 acceptance **12/12**；compileall、architecture strict 通过。
- 阻塞：无。
- 下一步：进入 M280-E 文档、提交推送和全局重规划。

### M280-E：阶段收口与全局重规划（进行中）

- 目标：记录 M280 的真实验收证据和 provider 失败边界，更新中文项目记忆/里程碑/快照，提交推送后从项目全局规划下一阶段。
- 改动：补充 M280 Plan/Spec 实际结论、中文问题日志、milestones；保留 provider 失败 receipt 与真实 GIS/Economic 恢复证据的分层结论。
- 待读/待修改：
  - `docs/agent-development-issues.md`
  - `docs/m280-real-composite-acceptance-plan.md`
  - `docs/m280-real-composite-acceptance-spec.md`
  - `docs/milestones.md`
  - `docs/agent-work-state.md`
  - `tasks/todo.md`
- 验证：待文档格式检查、git diff check、提交推送。
- 阻塞：无。
- 下一步：只读取上述文档尾部/相关段落，追加 M280 结论，不加载完整历史。

## 更新协议

1. 开始子任务：写入“进行中”、目标、明确文件和验证方式。
2. 完成子任务：补充实际改动、验证结果、阻塞和下一步。
3. 暂停或阻塞：保留可复现的阻塞原因和恢复条件，不把未知问题写成已完成。
4. 阶段完成：更新本账本、`docs/agent-work-state.md`、阶段文档和 `tasks/todo.md`，再提交推送并进行全局重规划。
