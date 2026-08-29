# M323 人工审批、持久化和 Registry 治理实施计划

状态：已完成。M323-A～D 已完成；实现前后维护 `handoff.md` 和 `tasks/current-state.md`。

## 任务包

### M323-A：审批契约和状态机 — 已完成

- [x] 建立 approval identity、receipt fingerprint、状态枚举和有界 decision receipt。
- [x] 定义合法状态转换、幂等规则、版本冲突和过期语义。
- [x] 补充 proposal receipt 到 approval record 的安全归一化。

### M323-B：持久化与恢复 — 已完成

- [x] 在 SQLite 增加审批记录和决策记录的版本化持久化边界。
- [x] 支持 pending/approved/rejected/expired/revoked 的重启恢复和状态校验。
- [x] 失效记录不得恢复为可执行状态；过期记录可通过状态筛选触发持久化转换。

### M323-C：Registry 发布与 Runtime gate — 已完成

- [x] 批准后生成版本化 ToolRegistry definition，避免直接加载任意源码。
- [x] 将 approval gate 接入 dispatch、动态工具快照和执行 evidence。
- [x] 撤销、版本漂移和未批准提案在执行前 fail closed。

### M323-D：共享应用边界与交付 — 已完成

- [x] 在共享 `HTTPApplication` 增加查询/批准/拒绝/撤销语义，保持 FastAPI/stdlib 一致。
- [x] 增加最小 CLI/HTTP contract 与状态矩阵测试，不复制传输层逻辑。
- [x] Docker 集中运行紧凑回归、compileall、architecture strict、readiness 和跨入口验收。
- [x] 更新阶段交接、任务账本、中文问题日志，准备提交并全局重规划 M324。

## 风险与验证点

- 未批准代码执行：用 registry names、dispatch 和 restart 三处门禁验证。
- 旧 receipt/新版本漂移：用 fingerprint 和 expected_version 验证拒绝。
- HTTP 双入口分叉：用共享 HTTPApplication 和一条 contract 对照验证。
- 文档恢复膨胀：阶段状态只写 handoff/current-state，历史进入 archive。

## 测试策略

开发期间只运行受影响的紧凑测试和语法检查；阶段收口运行一轮 Docker 审批契约、恢复、HTTP
contract、compileall、architecture strict 和 readiness。真实模型与 GIS 不在 M323 重复验收。

## M323 收口结果

- SQLite approval record、decision history、过期转换和重启恢复均通过紧凑契约。
- Registry 只接受 approved + 版本/指纹匹配的 definition；撤销和漂移在 dispatch 前 fail closed。
- HTTPApplication、FastAPI 和 stdlib 入口共享审批语义；测试边界使用独立临时 SQLite，避免生产状态污染。
