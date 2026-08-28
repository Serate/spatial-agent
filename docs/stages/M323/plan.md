# M323 人工审批、持久化和 Registry 治理实施计划

状态：规划中。实现前先维护 `handoff.md` 和 `tasks/current-state.md`。

## 任务包

### M323-A：审批契约和状态机

- [ ] 建立 approval identity、receipt fingerprint、状态枚举和有界 decision receipt。
- [ ] 定义合法状态转换、幂等规则、版本冲突和过期语义。
- [ ] 补充 proposal receipt 到 approval record 的安全归一化。

### M323-B：持久化与恢复

- [ ] 在 SQLite 增加审批记录和决策记录的版本化持久化边界。
- [ ] 支持 pending/approved/rejected/expired/revoked 的重启恢复和状态校验。
- [ ] 失效记录不得恢复为可执行状态。

### M323-C：Registry 发布与 Runtime gate

- [ ] 批准后生成版本化 ToolRegistry definition，避免直接加载任意源码。
- [ ] 将 approval gate 接入 dispatch、动态工具快照和执行 evidence。
- [ ] 撤销、版本漂移和未批准提案在执行前 fail closed。

### M323-D：共享应用边界与交付

- [ ] 在共享 `HTTPApplication` 增加查询/批准/拒绝/撤销语义，保持 FastAPI/stdlib 一致。
- [ ] 增加最小 CLI/HTTP contract 与状态矩阵测试，不复制传输层逻辑。
- [ ] Docker 集中运行紧凑回归、compileall、architecture strict、readiness 和跨入口验收。
- [ ] 更新阶段交接、任务账本、中文问题日志，提交推送并全局重规划 M324。

## 风险与验证点

- 未批准代码执行：用 registry names、dispatch 和 restart 三处门禁验证。
- 旧 receipt/新版本漂移：用 fingerprint 和 expected_version 验证拒绝。
- HTTP 双入口分叉：用共享 HTTPApplication 和一条 contract 对照验证。
- 文档恢复膨胀：阶段状态只写 handoff/current-state，历史进入 archive。

## 测试策略

开发期间只运行受影响的紧凑测试和语法检查；阶段收口运行一轮 Docker 审批契约、恢复、HTTP
contract、compileall、architecture strict 和 readiness。真实模型与 GIS 不在 M323 重复验收。
