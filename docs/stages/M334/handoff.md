# M334 阶段交接

## 状态

- 阶段：`M334` 多来源证据与跨域组合
- 状态：已完成并待提交推送
- 基线：`722db01`；本阶段工作区包含 M334 实现与验收入口修复
- 协作：单 Agent，最大并发度 1；Docker 优先，默认测试精简

## 目标与决策

M333 解决了受控网页搜索和读取；M334 解决多来源证据是否可去重、可判断新鲜度、可关联和可降级。证据质量是 Runtime 公共能力，不属于 GIS 或经济 Domain。首版不做 RAG、不做自动冲突裁决、不把正文持久化。

## 当前必要文件

- `docs/stages/M334/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/evidence/{contract.py,projection.py,registry.py}`
- `agent/evidence/{bundle.py,composite.py,identity.py,quality.py}`
- `agent/network/{web_search.py,web_fetch.py}`
- `agent/application/composite_view.py`
- `agent/result_summary.py`
- `agent/answer_generation.py`
- `agent/runtime_core/projection.py`
- `web/src/console_result_projection.js`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m334_evidence_quality.py`
- `tests/test_answer_generation.py`
- `tests/test_m177_evidence_projection.py`
- `tests/test_m178_contract_harness.py`
- `tests/test_m326_result_completeness.py`
- `tasks/current-state.md`
- `docs/agent-work-state.md`

## 恢复入口

只优先读取 `docs/agent-work-state.md`、`tasks/current-state.md` 当前区块、本 handoff、M334 plan 当前子任务和上面列出的必要文件；不要默认读取历史阶段文档、全量源码、全量测试、模型原文、网页正文或敏感配置。

## 阶段输入

- 产品：用户需要看到来源范围、时间和限制，不能只看到“完成了 N 个工具步骤”。
- Runtime：已有 Evidence Registry/Projection 和临时网页正文边界，应该扩展公共投影而不是再造 registry。
- Planner：ReAct 已能搜索和抓取，但仍需要依据证据缺口决定继续、澄清、降级或完成。
- Domain/数据：GIS、指标、文本结果要共享 provenance；范围、时间、单位和版本不一致时必须显式限制。
- 部署：默认离线测试，Docker 做集成，网络和真实模型只做显式验收。
- 测试：以 identity、quality、bundle、composite、恢复投影五类独立风险集中验证。

## 已完成实现

- Identity/Quality：来源定位、source id、内容指纹、freshness、completeness 和安全字段投影已版本化；缺失时间保持 unknown。
- Bundle：Web、GIS、指标来源可进入同一有界集合；输入排序确定、来源去重、重复 lineage、同一定位内容冲突、coverage 和 limitations 均可恢复。
- Composite：子结果保留 fact receipt、source_refs、scope 和跨域 alignment；范围/时间/单位不一致时只保留限制，不隐式拼接。
- Answer/Projection：答案上下文只读取安全 result summary/evidence bundle；过期、时间未知、部分、不可用和冲突来源有通俗中文降级提示；本地数据来源不会被误当成网页链接。同步、异步和 artifact 使用同一 evidence projection。
- Frontend：结果摘要展示规范来源数、去重/质量状态、冲突与对齐提示；本地 locator 以文本展示，网页来源才生成 HTTPS 链接。

## 当前验证

- M334 紧凑契约：`12/12` 通过；受影响回归：`56/56` 通过。
- Docker `quick + stage + smoke`、compileall、architecture strict、readiness `200` 和生产 HTTP acceptance 通过。
- 生产 acceptance 覆盖通用 Host/GIS Domain 能力快照、真实数据卷、preview、同步/Artifact、失败契约、异步恢复和幂等。
- 真实模型 + 本地 GIS + `public` 网页显式验收实际执行 3 个工具步骤，但 Provider 在有界预算内未完成；按安全 `provider_timeout`/网络不可用降级记录，未伪造来源。

## 阶段结束条件

M334-0～E 完成；多来源来源身份、质量、Bundle、跨域 Composite 和网络降级有版本化契约；Docker 集成、生产 HTTP acceptance 和一次真实模型显式验收完成；文档索引、中文问题日志、交接状态已更新，待提交推送。

## 全局重规划输入：M335

- 产品：让用户看到多来源事实、质量、限制和可读结论；网络不可达时仍能清楚区分“本地结果”“网页缺失”和“模型超时”。
- Runtime：优先建立 Provider/网络健康与预算反馈的统一 evidence；继续保持同步、异步、SSE、Artifact 和重启恢复同一结果契约。
- Planner：提高通用 ReAct 的多工具连续决策成功率，让模型根据证据缺口继续、澄清、降级或完成，而不是复制 GIS 专题流程。
- Domain/数据：验证 GIS、经济、指标和文本结果的多结果组合、范围/时间/单位对齐与部分成功表达；补充可发现的通用数据能力，不增加固定问句分支。
- 体验：前端以结构化阶段事件、来源质量和最终结论为主，详细证据可展开；地图/表格/指标视图继续由 Result/View 契约驱动。
- 部署/测试：提供 Provider 网络健康诊断和可重复 live 入口；默认保持离线精简，Docker/真实模型/真实网络为显式验收。

## 下一步

1. 创建 M335 capability map、Spec、Plan 和 handoff，优先处理 Provider/网络健康与通用多工具 ReAct 稳定性。
2. 阶段实现遵循“全局规划 → Spec → Plan → 实现 → 最小验证 → 交接 → 全局重规划 → 提交推送”。
