# Spec: M280 真实跨域 Composite 纵向验收

## Objective

验证从真实中转模型规划到真实 GIS/Economic 执行的完整跨域闭环。Provider 返回的 JSON 可能因中转兼容性、省略字段或旧式输出而轻微漂移；系统可以做有界、可审计的兼容归一化，但不得猜测 Domain、能力、事实或工具参数。任何归一化后的计划都必须再次通过 M279 candidate contract、Composite request schema 和 Host allowlist。

## Required

1. 建立独立 provider response normalizer：只允许文档化的字段别名/默认 outcome，不接受未知组件字段，不读取原文进入 public evidence。
2. 真实模型 planning probe 记录 planner source、compatibility action、schema status、组件数和 fingerprint，不记录模型原文。
3. 至少一条真实 GIS + Economic Composite：自然语言请求 → 合法 DAG → 真实数据执行 → `composite_result`。
4. 同一请求验证同步与 async 核心结果一致；async 轮询、artifact、SQLite detail、observability、evidence 的状态和 fingerprint 一致。
5. 构造 orphan async job，重启后只 claim 一次；已完成组件不重复执行。
6. provider 不可用、输出不合法、数据缺失时返回结构化拒绝/澄清/部分结果，不创建错误的 execution run。

## Deferred

- 前端动态 Composite 多面板完整交互。
- 自动新增工具、RAG、外部搜索和实时数据抓取。
- 默认 CI 网络依赖。

## Acceptance

- 离线 fake/replay 覆盖合法旧式输出、非法字段、缺少 outcome、provider error 和 capability mismatch。
- 显式 live 中转至少完成 provider → planner contract；若模型仍不能生成合法 DAG，保留失败 receipt，不伪装成功。
- 真实数据验收只在 Docker 显式执行，结果不进入仓库。
- M279/M278 回归、compileall、architecture strict、CI/stage 通过。

## Public boundary

`CompositePlanningResponse` 增加 bounded `compatibility` 与 `planner_evidence` 摘要；现有 `spatial-agent.composite-request.v1`、`composite_result` 和 M278 lifecycle 不改版本。
