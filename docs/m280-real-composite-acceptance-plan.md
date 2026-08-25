# Plan: M280 真实跨域 Composite 纵向验收

1. **Response compatibility**：先写 normalizer Spec/contract，支持有限字段别名/默认值；非法字段 fail closed。
2. **Planner evidence**：把 compatibility action、schema status、fingerprint 接入规划响应，保持脱敏。
3. **Offline replay**：用 fake/replay 验证合法计划、repair、provider failure、capability mismatch 和不创建 run。
4. **Live planning**：在 Docker 中显式运行中转 planning probe；按 provider/contract 分层记录，不自动重试昂贵请求。
5. **Real execution**：用合法计划执行 GIS + Economic，比较 sync/async/result/artifact/evidence；必要时再做 orphan restart 验收。
6. **Global review**：更新工作快照、中文问题日志、里程碑并推送；再规划前端动态 Composite View。

## 读取范围

- `docs/m280-real-composite-acceptance-spec.md`
- `docs/m280-real-composite-acceptance-plan.md`
- `agent/composite_planner.py`
- `agent/application/composite_planning.py`
- `tests/test_m279_composite_planner.py`
- 后续任务明确列出的 live/evaluation 文件
