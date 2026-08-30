# Plan：M329 通用请求路由与跨域能力汇聚

> 执行顺序：文档初始化 → 契约 → 能力汇聚 → Runtime → 入口 → 恢复 → 精简验收 → 交接/提交/全局重规划。单 Agent，最大并发度 1。

## M329-0：初始化

- [x] 建立 capability map、Spec、Plan、handoff。
- [x] 修正热状态与恢复入口，避免默认读取完整历史。
- [x] 更新任务账本；文档/代码索引在代码变更后统一重建。

## M329-A：Request Mode

- [x] 新增 `request-mode.v1` 归一化和安全投影。
- [x] 接入 `AgentRunResult`、SQLite/artifact、execution record 和终态事件。
- [x] 在 direct answer、tool、mixed、clarify、failure 路径统一推导模式。

## M329-B：General Capability Host

- [x] 聚合已登记 Domain Pack 的 capability、provider、权限和健康状态。
- [x] 实现工具 owner、dispatch、preflight 转发和 provider 局部降级。
- [x] 实现工具/结果类型冲突的 fail-closed 规则与稳定上下文指纹。

## M329-C：General Runtime

- [x] 构建通用 Runtime Pack/Factory，不携带 GIS 专用策略。
- [x] 默认接入真实模型 full ReAct、Web 搜索和受控工具提案。
- [x] 增加领域中立答案 fallback、部分结果和不确定性说明。

## M329-D：Product Entrypoints

- [x] `/runs`、异步、preview、events、artifact、retry/cancel/approval 默认使用通用 Runtime。
- [x] `/domains/{id}` 和旧 `/runs/auto` 保持兼容并明确语义。
- [x] CLI、前端默认切换为通用入口，继续消费统一 Result/Evidence。

## M329-E：Recovery

- [x] 验证多轮会话、SQLite、重启、Artifact、轮询、SSE/Last-Event-ID。
- [x] 验证通用 Runtime 中 proposal 审批后的同一 Run 恢复。
- [x] 验证旧显式 Domain Run 仍通过 Domain 入口可读。

## M329-F：验收与交付

- [x] 运行一个紧凑测试模块和必要相邻回归。
- [x] Docker readiness、compileall、architecture/index 和前端 smoke。
- [x] 真实模型 + Docker 完成普通回答、跨域工具/Web、不可用降级三类请求。
- [x] 更新交接文档、状态账本、索引，提交并推送版本，再进行全局重规划。

## 阶段结果

- Docker 紧凑回归 `18/18`，答案上下文定向回归 `15/15`；compileall、architecture strict、code/document index、
  readiness `200` 和前端 projection smoke 通过。
- 真实模型 + Docker 已验证通用直接回答、经济跨域工具链、白名单 Web 不可用降级、工具提案审批态和同一 Run 恢复。
- 产品 `/runs` 默认使用 `general` Runtime；显式 `/domains/{domain_id}` 保持 Domain 隔离，CLI 默认支持 `general`。
