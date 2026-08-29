# Plan：M328 受控开放行动闭环

> 顺序：全局重规划 → Spec → 实现 → 最小验证 → Docker/live 验收 → 交接更新 → 全局重规划 → 提交推送。
> 单 Agent，最大并发度 1；真实模型和 GIS 优先使用 Docker。

## M328-A：审批后的恢复闭环

- [x] 明确 `WAITING_FOR_DECISION`、approved、rejected、revoked 和 expired 的状态转移。
- [x] 让审批结果、ToolRegistry binding、run identity 和 artifact/recovery 共享 receipt fingerprint。
- [x] 验证审批前不执行、审批后只执行同一版本、拒绝后可读且不可执行。

## M328-B：Web evidence 可用性

- [x] 检查 provider 配置、allowlist、重定向、大小和超时的统一投影。
- [x] 为成功来源、无结果和网络不可用保留相同 document evidence contract。
- [x] 在答案/前端显示来源状态和限制，不把搜索失败当成来源成功。

## M328-C：跨域开放行动

- [x] 让 Composite/Domain ReAct 共享行动和结果摘要，不新增固定问句分支。
- [x] 验证经济本地数据、document evidence 和工具提案的多步组合及部分结果；GIS 缺失路径保留结构化降级。
- [x] 检查数据 freshness、缺失字段和 workflow 不可物化时的澄清/降级路径。
- [x] 重新执行最终脱敏验收 receipt，覆盖“本地数据 + Web 搜索 + 手搓工具/流程 + 流式答案”的复杂请求；跨域目录组合
  另行完成，过宽请求的澄清/拒绝边界也已验证。

## M328-D：体验与恢复验收

- [x] 前端展示搜索、审批、恢复和流式答案的阶段状态；技术详情保持折叠。
- [x] 验证断线、重启、轮询、SSE Last-Event-ID 和 Artifact 恢复的一致性。
- [x] 保持默认 CI 精简，live/Docker/browser 作为显式验收。

## M328-E：阶段收口

- [x] Docker 受影响回归、compileall、architecture strict、readiness。
- [x] 真实模型 + Docker/GIS、真实 Web 搜索和真实 proposal 已各完成至少一次脱敏验收；复杂跨域复验待执行。
- [x] 更新 `docs/agent-work-state.md`、`tasks/current-state.md`、`tasks/task-progress.md`、问题日志和索引。
