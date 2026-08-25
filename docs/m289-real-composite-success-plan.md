# M289 真实 Composite Planner 纵向成功链路 Plan

## 完整实施包

### M289-A：全局规划与验收矩阵

- 固定 success / clarification / rejection / provider failure / data unavailable 的公共状态和脱敏 receipt 字段。
- 复核 GIS/Economic catalog、readiness、TaskPlan bridge、answer/view/artifact/restart 的当前 seam。

### M289-B：Planner-to-TaskPlan 纵向收口

- 用一个 provider-neutral harness 运行真实或 replay Planner；保证同一 context、wire profile、canonical request fingerprint 和 TaskPlan gate。
- 对合法两域 DAG、未知能力和非法依赖保留最小负向证据，不修改 Runtime 权限。

### M289-C：真实 GIS/Economic 执行与恢复对照

- 用 Docker local 数据运行一条真实或安全失败的 Composite case。
- 对照 sync、async、artifact、SQLite restart 的 Result/View/Evidence；若 planner 失败，不伪造执行结果。

### M289-D：答案与前端验收

- 确认 Answer Generator 只基于 canonical facts 和 evidence 生成自然语言摘要。
- 前端展示结论优先、组件状态、限制、来源/证据和下一步，不增加领域专用页面分支。

### M289-E：集中门禁、live、文档与版本

- 只运行一组 compact replay/contract、一组跨入口 Docker acceptance、一次显式 live Composite probe。
- 更新中文问题日志、milestones、任务账本、恢复快照和 Goal 全局重规划，提交并推送版本。

## 测试策略

- 开发过程中只做必要的 compile/静态检查；M289-B～D 完成后集中运行一次 compact contract。
- 阶段收口保留 Docker、readiness、architecture strict、前端 projection 和一次 live；不按每个失败类型重复跑完整回归。
- live 失败也是有效证据，但必须验证未创建越权 run、状态/错误码可恢复且无敏感输出。

## 明确边界

- 不把真实 case 的区域名称、固定问句或某个指标写入公共 Runtime 分支。
- 不通过扩展 schema、增加 repair 次数或吞掉 provider error 来提高“成功率”。
- 新增能力优先体现在 Domain catalog、RequestFacts、工具 schema、workflow 和 Result 类型，而不是 Planner 特判。
