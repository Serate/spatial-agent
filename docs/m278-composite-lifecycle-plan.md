# Plan: M278 Composite 可恢复生命周期

## 实施顺序

1. **Composite Envelope**：为 `AgentRunResult` 增加可选 canonical `result`，让 SQLite rehydrate、artifact 读取和普通 Result Contract 构建能识别 Composite；补 envelope 回归。
2. **Composite Run Application**：新增 `CompositeRunApplication`，注入 M276 coordinator 与现有 `AsyncApplication`，实现同步持久化、异步幂等提交、worker 执行、取消/超时、artifact 写入、查询和重启 recovery；为 `composite` 使用独立持久化 scope。
3. **Shared HTTP Recovery**：扩展 `HTTPApplication` semantic commands，FastAPI/stdlib 增加 async/detail/observability/evidence 路由，transport 不实现生命周期。
4. **Docker 集成验收**：运行 M278 定向测试、compileall、architecture strict、CI/stage 和最小 HTTP async/recovery 验收。
5. **文档与交付**：更新中文恢复卡、里程碑和问题日志，提交并推送 M278；随后基于项目全局规划 LLM Composite Planner 与通用前端 Composite View。

## 关键接口

- `CompositeRunApplication.run(request, session_id, export_artifact)`
- `CompositeRunApplication.submit_async(request, session_id, idempotency_key, export_artifact)`
- `CompositeRunApplication.get_run(run_id)`
- `CompositeRunApplication.get_observability(run_id)`
- `CompositeRunApplication.get_evidence(run_id)`
- `CompositeRunApplication.recover()`

## 风险与缓解

- Composite Result 被普通 Result Contract 再包装：增加 canonical result 检测，恢复时优先 normalize 已有 Composite envelope。
- Synthetic `composite` scope 与 Domain 记录串线：所有 SQLite/artifact 读写都带 `domain_id=composite`，并用独立 artifact namespace/identity 检查。
- 异步完成与 artifact 写入时序不一致：先写 SQLite terminal snapshot，再以 terminal observability 重写 artifact；恢复测试检查最终状态而不是中间时序。
- 重启重复执行：沿用 AsyncApplication 的 owner_pid claim/recovery，组件执行 receipt 由 coordinator 结果持久化；只对未完成的 Composite job 接管。
- 两个 HTTP 入口语义漂移：新增命令只在 HTTPApplication 实现一次，入口只映射 URL 和资源 ID。

## Verification Checkpoints

| Checkpoint | Evidence |
|---|---|
| Envelope | SQLite roundtrip 返回相同 Composite schema/version/fingerprint |
| Async | 同 idempotency key 只有一个 job，轮询最终状态与 result 一致 |
| Artifact | 删除/绕过 SQLite 读取时仍能恢复 canonical result/evidence |
| Restart | orphan job 被 claim 一次，组件执行次数满足依赖顺序 |
| HTTP | FastAPI/stdlib 都调用同一 semantic command，Docker health 200 |
