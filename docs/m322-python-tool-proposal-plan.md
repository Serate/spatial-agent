# M322 Python 工具提案与 Docker 沙箱实施计划

状态：已完成。恢复入口为 [`docs/agent-work-state.md`](agent-work-state.md)，短账本为
[`tasks/task-progress.md`](../tasks/task-progress.md)。

## 任务包

### M322-A：契约与安全策略

- [x] 建立能力图、Spec、Plan 和 M322 交接入口。
- [x] 固定 `tool-proposal.v1`、receipt、source/schema hash 和 reason code。
- [x] 扩展 ReAct proposal schema，源码继续从事件/evidence 中剥离。

### M322-B：静态校验与沙箱协议

- [x] 实现名称/schema/source 规范化和 AST allowlist。
- [x] 实现有界 Unix socket client/worker 协议和安全 receipt。
- [x] worker 重复静态检查，并校验示例输入、JSON 输出和 output schema。

### M322-C：Docker sidecar 与 Runtime/ReAct 接入

- [x] 在 compose 增加无网络、只读、tmpfs、资源受限的 sandbox sidecar，不挂载 Docker socket。
- [x] Runtime 注入 proposal validator；ReAct `propose_tool` 形成待审批终态和可恢复 evidence。
- [x] 验证提案不注册、不修改 Registry，也不能作为后续工具执行。

### M322-D：紧凑验证与交付

- [x] 增加 AST、worker、client、ReAct/Runtime 和安全投影的最小契约测试。
- [x] Docker 集中运行 sidecar 场景、M322/M321/M320、compileall、architecture strict 和 readiness。
- [x] 更新交接、任务账本和中文问题日志，提交推送并全局重规划 M323。

## 阶段验收

- Docker M322 契约测试 **7/7**；本次 Docker M318/M319/M320/M321/M322 合并回归 **43/43**。
- Docker `compileall`、`architecture_check.py --strict`、`smoke_check.py` 和 `/health/ready` **200** 通过。
- 主服务通过共享 Unix socket 调用无网络 sidecar，纯计算提案返回 `validated / proposal_validated`；SQLite receipt 恢复通过。
- sidecar healthcheck 不再向 worker 建立后立即断开的连接写回；client、worker、runner 只传输公开 proposal 字段，避免内部 hash 字段重复规范化。
- receipt 仅保存脱敏 identity、hash、检查状态、耗时、输出字节数和 sandbox profile；未自动注册、未在主进程执行生成代码，未调用真实模型。

## 固定约束

- 单 Agent、最大并发 1；Python 和验收使用 Docker。
- 提案默认开启，但 sidecar 不可用时不得在主进程降级执行。
- M322 只交付“提案 + 验证 receipt”，M323 才实现人工审批、持久化状态机和 Registry 注册。
