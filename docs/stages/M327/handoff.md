# M327 阶段交接

## 状态

- 阶段：`M327` 开放请求能力发现与结果质量
- 状态：规划完成，尚未实现
- 当前任务：M327-A 能力描述契约
- 恢复入口：优先读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本文件和 `plan.md` 中当前批次；不读取完整历史

## 已完成

- 已从产品体验、Runtime 架构、Domain 扩展、数据、模型、部署和测试七个维度完成全局重规划。
- 已建立 Capability Map、Spec 和分批 Plan；首版不引入 RAG、自动数据下载或模型生成工具自动上线。

## 进行中

- M327-A：确定通用 capability descriptor 的最小字段和兼容策略。

## 必要文件

- `agent/capability_catalog.py`
- `agent/application/catalog.py`
- `agent/domain_contract.py`
- `agent/result_contract.py`
- `agent/result_completeness.py`
- `agent/evidence/projection.py`
- `agent/llm_planner.py`
- `tests/test_m326_result_completeness.py`

## 验证与边界

- M326 阶段 Docker 紧凑回归 `49/49`、compileall、architecture strict、readiness `200` 和真实 Docker/GIS 验收已完成。
- M327 继续采用单 Agent、最大并发度 1；Python、GIS、测试和阶段验收优先在 Docker 中运行。
- 不提交 API key、Prompt、模型原文、真实数据和临时输出。

## 下一步

先读取 M327-A 必要源码，冻结 descriptor 契约；每个子任务完成后更新本文件、`docs/agent-work-state.md`
和 `tasks/task-progress.md`，再执行受影响的最小验证。
