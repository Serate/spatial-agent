# Spec：M334 多来源证据与跨域组合

## Objective

面向通用 Agent Runtime 建立可信的多来源证据层。用户提出需要比较、汇总、解释或跨领域分析的问题时，Runtime 能够合并网页、GIS、指标和文本结果，标识来源、时间、新鲜度、覆盖范围和限制，并让最终答案只使用已校验的证据投影。

本阶段不建设行业知识库、不引入 RAG、不保证来源事实绝对正确，也不为经济、GIS 或其它专题增加硬编码流程。它只提供通用来源质量和组合契约。

## Tech Stack

- Python 标准库和现有 `agent/evidence/`、Result Registry、ToolRegistry、ReAct、SQLite/Artifact、SSE 组件。
- 现有 Web Search/Fetch 和 Domain Pack 适配器。
- 不新增网络依赖，不把完整网页正文写入持久化存储，不要求默认 CI 访问外网。

## Public Contracts

### Evidence Source Identity

每个来源使用版本化安全投影，至少包含：`schema_version`、`source_id`、`kind`、`locator`、`title`、`retrieved_at`、`published_at`（可空）、`content_hash`（可空）、`status` 和 `quality`。`source_id` 由规范化来源定位和内容指纹稳定生成；凭据、正文、Prompt 和模型原文永不进入投影。

### Evidence Quality

质量状态只能来自可审计输入：`available`、`stale`、`partial`、`duplicate`、`unavailable`、`unknown`。返回 `freshness`、`completeness`、`reason_codes` 和有界计数，不输出未经证实的“可信度百分比”。时间缺失时必须是 `unknown`，不能默认新鲜。

### Evidence Bundle

Bundle 是有界来源集合，包含 `schema_version`、`entries`、`unique_count`、`duplicate_count`、`coverage`、`limitations` 和 `quality_summary`。同一来源只保留一个 canonical entry，保留安全的 duplicate lineage；完整网页正文仍仅存在当前 Run 的临时模型上下文。

### Cross-domain Composite

Composite 只能引用已校验的 Result 或 Evidence entry。每个事实必须带 `fact_id`、`source_refs`、`data_kind` 和 `status`；不能因为多个来源存在就推导出未经工具计算的数值或结论。无法对齐的空间范围、时间范围、单位或数据版本必须进入 `limitations`。

## Project Structure

- `agent/evidence/identity.py`：来源身份和安全规范化。
- `agent/evidence/quality.py`：新鲜度、完整性和质量 receipt。
- `agent/evidence/bundle.py`：来源聚合、去重和缺口投影。
- `agent/application/composite_view.py`、`agent/result_summary.py`：消费通用 bundle，不添加领域分支。
- `agent/answer_generation.py`：只把 bounded evidence context 交给模型，保留结构化质量限制。
- `tests/test_m334_evidence_quality.py`：紧凑离线契约回归。
- `docs/stages/M334/`：阶段设计与交接材料。

## Code Style

证据模块使用纯函数或小型深模块，输入 `Mapping`，输出新的有限 `dict`，不修改调用者对象；非法或缺失数据采用结构化 `reason_codes`，避免抛出暴露内部文本的异常。公共函数命名使用 `build_`、`normalize_`、`project_`，schema 常量只在 canonical 模块声明。

```python
bundle = build_evidence_bundle(entries, now=clock.now())
assert bundle["schema_version"] == "spatial-agent.evidence-bundle.v1"
assert all("source_refs" in fact for fact in composite["facts"])
```

## Testing Strategy

- 默认阶段门禁：M334 紧凑契约测试、受影响的 Evidence/Composite/答案测试、compileall、architecture strict、readiness。
- 使用固定时钟和 fake entries 验证来源规范化、重复、过期、缺少时间、部分结果、跨域限制和敏感字段投影。
- Docker 只在阶段收口验证持久化、HTTP/SSE/Artifact 和已有 GIS/真实模型链路；真实网络仍为显式验收，不进入默认 CI。
- 不因为来源数量增加而复制测试；每个测试覆盖一种独立失败模式。

## Boundaries

- Always：只使用结构化 Result/Evidence；所有 bundle 有上限；来源状态和限制可追溯；跨域组合保留 source refs。
- Ask first：改变 Evidence schema、默认新鲜度策略、增加外部搜索 Provider、引入数据库或 RAG。
- Never：把重复来源计作多个独立事实；以 URL 存在推断页面内容正确；把过期或不可用来源当作当前事实；持久化网页正文、Prompt、模型原文或密钥。

## Success Criteria

1. 同一 URL、同一内容或同一数据版本重复出现时，bundle 能稳定去重并保留安全 lineage。
2. 来源发布时间、抓取时间和缺失时间能分别表达新鲜、过期、未知和不可用，不把未知当新鲜。
3. 网页、GIS 和指标结果能够进入同一 Composite evidence 投影，事实、来源和限制可逐项关联。
4. 搜索/抓取不可用时，Runtime 能保留本地结果或直接回答，并明确说明缺少的实时证据。
5. SQLite、Artifact、HTTP、SSE、恢复和前端只消费安全质量投影，不泄漏正文或模型原文。
6. 一条 Docker 真实模型 + 本地 GIS + 受控网页的跨来源验收能够完成，失败时也有结构化降级。

## Open Questions

- 首版新鲜度阈值按来源类型配置，但不为具体行业写死；没有 `published_at` 的来源只能根据 `retrieved_at` 给出有限状态。
- 首版不做自动事实冲突裁决；冲突来源应并列保留并提示用户。
