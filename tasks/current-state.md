# 当前任务状态

> 热状态文件，只保留当前阶段和最近一个交接点，建议控制在 60 行以内。历史过程见
> `task-progress.md`，默认恢复不读取历史账本。

## 当前阶段

- 阶段：`M327`
- 当前任务：M327-A 能力描述契约
- 状态：规划完成，尚未实现
- 最近交付：M326 开放式 ReAct 稳定交付、真实 Docker/GIS 验收和跨入口恢复对照已完成

## 已完成

- M322 Python 工具提案、AST 校验、无网络 Docker sidecar 和待审批 receipt 已完成。
- 文档恢复架构重构方案已确定：热索引、阶段包、稳定知识、历史归档四层。
- 文件功能索引生成器、校验器和恢复主题查询已接入，覆盖 299 个源码文件。

## 进行中

- M323-A～D 已完成；审批状态、SQLite 恢复、Registry gate 和 HTTP 语义已闭合。
- M324 已完成：Runtime 创建时从 approval store 读取 approved 记录，仅通过 Registry 发布；handler 不可用时返回 degraded，不读取源码；前端消费版本化审批可见投影。
- P2 Persistence 已迁移至 `agent/persistence/`，根路径保留单向兼容 facade。
- P3 Provider Integration 已迁移至 `agent/integration/`，根路径保留单向兼容 facade。
- M323 修复了测试复用生产 SQLite 状态、SQLite 恢复丢失 definition、过期状态筛选遗漏三个问题，并补充回归覆盖。
- M325 修复了非策略类 ReAct 后续动作校验失败不能利用已有证据安全收束的问题。
- M326 已完成：开放 ReAct 不再继承自动模板的步骤/工具限制；Result、evidence、Artifact、SSE 和答案层统一表达部分结果；
  Artifact 原子发布、Provider 空响应错误边界和 live 验收判定已收口。
- M327 已完成全局重规划、Capability Map、Spec 和 Plan；首批任务是建立通用 capability descriptor，不引入 RAG 或自动工具上线。

## 必要文件

- `docs/stages/M327/handoff.md`
- `docs/stages/M327/spec.md`
- `docs/stages/M327/plan.md`
- `agent/capability_catalog.py`
- `agent/application/catalog.py`
- `agent/domain_contract.py`
- `agent/result_contract.py`
- `agent/result_completeness.py`
- `agent/evidence/projection.py`
- `tests/test_m326_result_completeness.py`

## 验证

- M326 Docker 阶段紧凑回归 `49/49`、Artifact/Provider 定向回归、compileall、architecture strict 和 readiness `200` 通过。
- 真实 Docker/GIS：sync/async/polling/artifact/evidence/SSE/Last-Event-ID/restart 对照通过；真实数据仅一次性只读挂载。

## 阻塞与下一步

- 阻塞：无。
- 下一步：读取 M327-A 必要源码，冻结 descriptor 最小契约；完成后立即更新交接文档和任务账本，再运行受影响的最小验证。
