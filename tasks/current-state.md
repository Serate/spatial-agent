# 当前任务状态

> 热状态文件，只保留当前阶段、进行中任务、必要文件和最近验证。历史过程按需从阶段 handoff 或归档读取。

## 当前阶段

- 阶段：`M334` 多来源证据与跨域组合
- 当前任务：M334-A 来源身份与质量深模块
- 状态：M334-0 已完成，等待实现来源身份与质量
- 基线：`722db01`
- 协作：单 Agent，最大并发度 1；测试、GIS 和 live 验收优先使用 Docker

## 当前必要文件

- `docs/stages/M334/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/evidence/{contract.py,projection.py,registry.py}`
- `agent/network/{web_search.py,web_fetch.py}`
- `agent/application/composite_view.py`
- `agent/result_summary.py`
- `agent/answer_generation.py`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m334_evidence_quality.py`
- `docs/agent-work-state.md`

## 当前决策

- M333 已推送：`722db01`；默认 Web 模式仍为 `allowlist`，`public` 必须显式开启。
- M334 只建设通用证据身份、质量、Bundle 和跨域 Composite；不引入 RAG、不持久化网页正文、不自动裁决冲突来源。
- 旧 Evidence payload 必须可读取；缺失时间表示 `unknown`，不能默认新鲜。

## 最近验证

- M333：本机 `11/11`；Docker M333 + M321 + M320 `43/43`；compileall、architecture strict、readiness `200` 和真实模型 + 公共 HTML 验收通过。

## 下一步

- M334-0 文档索引校验已通过；下一项是实现来源身份与质量深模块。
- 阶段收口统一执行精简门禁和 Docker/真实模型显式验收，并更新 handoff 后提交推送。
