# Plan：M335 通用多工具执行与 Provider 健康

> 单 Agent，最大并发度 1；每个子任务先更新 `docs/agent-work-state.md` 与 `tasks/task-progress.md`，测试遵循最小充分原则。

## M335-0：阶段初始化与契约冻结

- [x] 建立 Provider Health、ReAct composition 和 Result closure 的版本边界。
- [x] 检查 M334 的 Evidence Bundle、RunBudget、RunEvent 和当前恢复入口，避免重复造契约。
- [x] 写入当前必要文件与阶段交接规则。

验证：M335 阶段包、恢复入口和文档索引已建立；未修改 M335 业务代码。

## M335-A：Provider/网络健康与失败归因

- [ ] 统一模型、搜索、网页读取和 Domain provider 的安全状态投影。
- [ ] 区分 timeout、unavailable、invalid_response、policy_blocked、data_unavailable 和 retryable。
- [ ] 将健康事实接入 Runtime evidence、SSE、Artifact 和答案降级。
- 验证：fake provider 紧凑契约 + Docker readiness。

## M335-B：通用多工具 ReAct 稳定性

- [ ] 检查并修复多轮动作的上下文裁剪、重复动作、循环、预算和停止判断。
- [ ] 让能力目录、结果类型和工具 schema 驱动动作，不增加专题关键词分支。
- [ ] 保持结构化动作完整校验后才执行或展示。
- 验证：两个以上 Domain 的 fake 多工具组合、澄清、有限恢复和部分成功。

## M335-C：多结果闭合与答案质量

- [ ] 统一跨结果 source refs、质量、alignment、limitations 和 partial 状态。
- [ ] 让答案生成读取安全 Bundle 并给出简洁结论、来源范围和缺口说明。
- [ ] 前端按 Result/View 契约动态展示，不扫描工具名推断页面。
- 验证：GIS + economic/text 混合结果的跨入口一致性。

## M335-D：实时体验与恢复验收

- [ ] 验证复杂请求的阶段事件、心跳、答案增量、取消、重试和断线恢复。
- [ ] 检查同步、异步、SSE、轮询、Artifact、SQLite 重启接管的 identity 和 evidence 一致。
- 验证：Docker 精简集成和一次真实模型显式验收。

## M335-E：阶段收口与全局重规划

- [ ] 更新中文问题日志、模块职责、代码/文档索引和 handoff。
- [ ] 提交并推送版本。
- [ ] 从产品、Runtime、Planner、Domain/数据、部署和测试全局规划下一阶段。

## 阶段门禁

- 文档索引校验、受影响紧凑测试、compileall、architecture strict。
- Docker readiness、SQLite/Artifact/SSE 恢复和跨入口契约。
- 真实模型/网络只走显式有界验收，不进入默认 CI。
