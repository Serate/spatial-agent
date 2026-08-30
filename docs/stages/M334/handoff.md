# M334 阶段交接

## 状态

- 阶段：`M334` 多来源证据与跨域组合
- 状态：规划已建立，代码实现尚未开始
- 基线：`722db01`
- 协作：单 Agent，最大并发度 1；Docker 优先，默认测试精简

## 目标与决策

M333 解决了受控网页搜索和读取；M334 解决多来源证据是否可去重、可判断新鲜度、可关联和可降级。证据质量是 Runtime 公共能力，不属于 GIS 或经济 Domain。首版不做 RAG、不做自动冲突裁决、不把正文持久化。

## 当前必要文件

- `docs/stages/M334/{capability-map.md,spec.md,plan.md,handoff.md}`
- `agent/evidence/{contract.py,projection.py,registry.py}`
- `agent/network/{web_search.py,web_fetch.py}`
- `agent/application/composite_view.py`
- `agent/result_summary.py`
- `agent/answer_generation.py`
- `agent/runtime_core/react_runtime.py`
- `tests/test_m334_evidence_quality.py`
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

## 阶段结束条件

M334-0～E 完成；多来源来源身份、质量、Bundle、跨域 Composite 和网络降级有版本化契约；Docker 集成与一次真实模型验收完成；文档索引、中文问题日志、交接状态更新后提交推送。
