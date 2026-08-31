# 当前任务状态

> 热状态文件，只保留当前阶段、进行中任务、必要文件和最近验证。历史过程按需从阶段 handoff 或归档读取。

## 当前阶段

- 阶段：`M335` 通用多工具执行与 Provider 健康
- 当前任务：M335-A Provider/网络健康与失败归因
- 状态：M334-A～E 已完成并收口；M335-0 阶段初始化与契约边界已完成，下一步实现 Provider Health
- 基线：`722db01`
- 协作：单 Agent，最大并发度 1；测试、GIS 和 live 验收优先使用 Docker

## 当前必要文件

- `docs/stages/M335/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/evidence/{contract.py,projection.py,registry.py}`
- `agent/evidence/{bundle.py,composite.py,identity.py,quality.py}`
- `agent/runtime_core/{run_budget.py,progress.py,react_runtime.py}`
- `agent/network/{web_search.py,web_fetch.py}`
- `tests/test_m334_evidence_quality.py`
- `docs/agent-work-state.md`

## 当前决策

- M333 已推送：`722db01`；默认 Web 模式仍为 `allowlist`，`public` 必须显式开启。
- M334 只建设通用证据身份、质量、Bundle 和跨域 Composite；不引入 RAG、不持久化网页正文、不自动裁决冲突来源。
- 旧 Evidence payload 必须可读取；缺失时间表示 `unknown`，不能默认新鲜。

## 最近验证

- M334：受影响回归 `56/56`；Docker `quick + stage + smoke`、compileall、architecture strict、readiness `200` 和生产 HTTP acceptance 通过。
- 真实模型 + 本地 GIS + `public` 网页请求实际执行 3 个工具步骤，但 Provider 在有界预算内未完成；已记录 `provider_timeout`/网络不可用安全降级。

## 下一步

- M334-A～E 已完成；阶段交接、中文问题日志、代码/文档索引已更新，待提交推送。
- 提交后进入 M335，优先处理 Provider/网络健康、通用多工具 ReAct、多结果组合、数据对齐和全局实时体验。
