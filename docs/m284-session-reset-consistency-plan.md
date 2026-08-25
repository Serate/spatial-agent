# Plan: M284 会话清空与跨入口状态一致性

## 实施顺序

1. **A 规划与边界**：✅ 完成 capability map、Spec、Plan，确认不修改 Runtime/Planner/ToolRegistry/Result schema。
2. **B reset boundary**：✅ 扩展 RendererRegistry 的有界 reset context；让 adapter 清理自己拥有的 surface 和内部 selection，不在 Console 主流程增加 GIS 分支。
3. **C stale-render guard**：✅ 复核并补齐 clear/session/domain generation 的传递；保证旧的异步 render、history restore 和 evidence hydration 不得回写。
4. **D 精简验收**：✅ 新增 Node reset contract；修复并串行运行地图 browser smoke；复用 M283 projection smoke 检查无回归。
5. **E 收口与全局重规划**：进行中，更新中文问题日志、milestones、恢复账本，提交推送版本；从全局目标规划下一阶段。

## 文件边界

- B：`web/src/console_renderer_registry.js`、`web/src/console_gis_plugin.js`
- C：`web/src/console_app.js`
- D：`scripts/console_reset_contract_smoke.js`、`scripts/console_map_smoke.js`
- E：`docs/agent-development-issues.md`、`docs/milestones.md`、`tasks/*`、`docs/agent-work-state.md`

## 风险与控制

- Adapter 清理不完整：Node fake adapter contract + 浏览器真实地图双重验证。
- 清理后旧请求回写：使用已有 generation guard，不用延时或忽略异常。
- 服务端 clear 失败：前端先保持安全空态，再展示有界错误，不调用历史恢复覆盖空态。
- 测试膨胀：只保留 reset 正向、stale render 负向和一条 browser regression。
- 领域耦合：architecture/static grep 检查公共 Registry 与 Console 不出现 GIS 专用判断。

## Verification Checkpoints

- B：Node reset contract 的 fake adapter 与 surface 清理断言。
- C：旧 render 返回 `superseded`，clear 后 context 为空。
- D：Docker readiness、Node reset smoke、串行 map browser smoke、M283 projection smoke。
- E：中文日志、阶段 milestone、恢复快照、git diff/push 和全局重规划。
