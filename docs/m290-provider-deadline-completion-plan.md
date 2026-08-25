# M290 Provider Deadline 与真实 Composite 完成 Plan

## 完整能力包

### M290-A：全局 deadline/timeout 状态建模

- 盘点 client timeout、live harness deadline、async worker 和 restart claim 的时序。
- 冻结 provider/harness/deadline 三类 receipt 及无 run 不变量。

### M290-B：Provider 与 harness deadline 对齐

- 让显式 live acceptance 传递同一有界 budget，避免 worker deadline 早于 provider client timeout 后仍占用资源。
- 保持默认生产配置保守，live budget 只能在显式 harness 参数中提高。

### M290-C：超时恢复与跨入口一致性

- 用 replay/fake 证明 planning timeout 不创建 run；execution timeout 的既有 SQLite/artifact/restart 语义不被破坏。
- 检查 HTTP、CLI、async polling 和 evidence projection 的相同错误分类。

### M290-D：真实 Composite 纵向验收与用户体验

- 一次真实模型 + local GIS/Economic case；成功则验证 Result/Answer/View，失败则记录安全 timeout/provider receipt。
- 前端显示结论优先的 timeout、限制和下一步。

### M290-E：集中门禁、文档、版本和全局重规划

- 只运行 compact deadline/lifecycle contract、Docker readiness/architecture/frontend gate 和一次 live。
- 更新中文日志、milestones、任务账本、恢复快照并推送版本。

## 边界

- 不增加 repair 次数、不放宽 schema、不新增 provider 特殊字段到 Domain/Runtime。
- 不为某个区域或固定 Composite 问句增加超时/工具分支。
