# Spec：M327 开放请求能力发现与结果质量

## Objective

让用户提出未预定义的开放问题时，真实模型可以从已登记能力中理解输入需求、选择可用能力、说明
选择依据，并把不同类型的结构化结果汇总成简洁、可审计的答案。GIS 仍是首个业务载体，但公共
Runtime 不携带 GIS 专用策略，也不把固定关键词当作能力边界。

用户价值：用户看到的是“系统发现了哪些可用信息、完成了什么、结论是什么、还缺什么”，而不是
工具名、内部字段或手写的单一专题模板。

## Commands

```text
Build: docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
Targeted: docker compose --env-file .env.production -f docker-compose.prod.yml run --rm spatial-agent python -m unittest tests.test_m327_result_summary tests.test_m326_result_completeness tests.test_m313_answer_stream -v
Compile: docker compose --env-file .env.production -f docker-compose.prod.yml run --rm spatial-agent python -m compileall -q agent domains scripts
Architecture: docker compose --env-file .env.production -f docker-compose.prod.yml run --rm spatial-agent python scripts/architecture_check.py --strict
Readiness: Invoke-WebRequest -Uri http://127.0.0.1:8088/health/ready -UseBasicParsing
```

真实模型、真实 GIS、网络和浏览器只通过显式验收脚本运行，不进入默认离线门禁。

## Project Structure

```text
agent/                         公共 Runtime、目录、Result/Evidence 和 ReAct 契约
agent/application/             HTTP/CLI/会话用例与跨入口投影
agent/runtime_core/            生命周期、计划、策略、恢复和执行投影
domains/*/                     Domain Pack 的能力描述、数据和工具实现
docs/stages/M327/               本阶段 capability map、Spec、Plan、handoff
tests/                          精简的契约和跨入口验证
web/src/                        结构化能力选择、结果和证据的前端消费者
```

## Code Style

能力描述必须是结构化数据，使用稳定 identity，不把模型自然语言直接当作执行输入：

```python
CapabilityDescriptor(
    capability_id="gis.raster.metadata",
    input_facts=("dataset_ref",),
    output_profile="raster_metadata_result",
    evidence_requirements=("dataset_provenance",),
)
```

公共层使用领域中立命名；新增字段应版本化并提供有界兼容读取。用户摘要使用通俗中文，详细
技术字段只放在可展开的证据区域。

## Testing Strategy

- 契约测试：能力描述、选择摘要、结果摘要和 identity 稳定性。
- 集成测试：同一请求通过 Runtime、HTTP、Artifact/恢复和前端投影时，核心结果与 evidence 一致。
- Docker 门禁：只运行受影响紧凑测试、compileall、architecture strict 和 readiness。
- 显式验收：阶段最多一次真实模型 + Docker/GIS 纵向请求；不保存 Prompt、模型原文、密钥或真实私有结果。

## Boundaries

- Always：通过 Capability Catalog 和 ToolRegistry；校验输入、权限、审批、数据就绪、结果和 evidence；保留可恢复状态。
- Ask first：新增外部数据源、扩大网络白名单、引入运行时依赖、改变公共契约或 CI 触发策略。
- Never：为单一区域/固定问句增加专用分支；执行未登记工具；提交密钥、模型原文、真实数据或绕过治理门禁。

## Success Criteria

1. 开放请求能获得有界的能力候选及其输入/输出/前置条件摘要，未知能力返回结构化澄清。
2. 真实模型或规则 Planner 产生的能力选择都能映射到公共 identity，并经过同一执行门禁。
3. 跨矢量、栅格和指标结果的答案摘要动态生成，不依赖 GIS 专用页面分支，并明确限制与证据来源。
4. CLI、HTTP、前端、Artifact 和恢复对同一请求保持核心结果、能力 identity 和 evidence 一致。
5. 默认测试精简且离线；Docker/真实模型验收可复现且不泄露敏感内容。

## M327-C 契约冻结：跨类型结果摘要

公共 Runtime 新增 `spatial-agent.result-summary.v1` 投影。它接收已经通过
`Result` 契约校验的结果、`completeness`、typed sections 和 evidence，输出有界的
`blocks`、`limitations` 和 `evidence`。每个 block 至少包含稳定的 `block_id`、
`kind`、`result_type`、`state`、`conclusion`、可展开的 `facts`、限制和 evidence
摘要；`kind` 只能来自公共 `data_profile`，首版覆盖 `vector`、`raster`、`metrics`、
`timeseries`、`text`、`document_evidence` 和 `composite`。

摘要只允许传播用户可读结论、有限标量/短列表和 evidence 状态，不传播 Prompt、模型
原文、工具参数、坐标数组、几何 features、路径、密钥或任意内部引用。未知或非法的
typed section 降级为 `unknown`/不可用 block，而不是让公共层猜测 Domain 语义。

答案生成上下文只消费该摘要投影；结构化 Result、View 和完整 evidence 仍分别保留，
因此“结论优先、技术详情可展开”由契约层保证，而不是由前端或 GIS 页面分支保证。

## M327-D 跨入口与前端接入

`result_summary` 是同步 Result、异步结果证据、Artifact、恢复证据和 Composite evidence
共同消费的唯一摘要投影。同步/恢复响应可在顶层提供同值别名，但嵌套 Result 始终是规范来源；
Artifact 只保存该有界投影，不重新拼接答案。异步运行尚未完成时可以不提供摘要，完成后应与
规范 Result 的摘要逐字段一致。

Console 先读取版本化 `result_summary`，以领域中立方式显示结论、关键发现、结果明细、限制和
证据来源；地图、图表等 View 通过 Renderer Registry 作为可选展示面，不得成为摘要的替代品。
未知摘要版本或非法 block 必须降级为空态，不能把任意对象直接拼接成 `[object Object]`，也不能
显示路径、坐标、Prompt、模型原文或密钥。

## Open Questions

- 首版只消费已有 Domain Catalog，不在 M327 引入 RAG、自动下载或模型生成工具的自动上线。
- 是否允许用户在能力候选中手动调整执行范围，留到结果质量验收后再决定。
