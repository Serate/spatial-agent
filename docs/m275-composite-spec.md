# M275 Spec：领域中立 Composite 结果与证据契约

## Objective

为跨领域逻辑请求提供版本化、可验证的 Composite 边界。一个 Composite 请求由若干已登记 Domain 的组件组成；每个组件最终可以复用现有 Agent Runtime 产生一个标准 Result Envelope。公共接缝只负责输入约束、聚合和投影，不解释 GIS 或 Economic 业务语义。

## 假设

1. 当前 Runtime 的执行单位仍是单 Domain；M275 通过独立契约承接未来的跨 Domain coordinator。
2. Domain 身份最终必须由 `DomainRuntimeHost`/Catalog 再次 allowlist 校验；契约规范化不替代权限校验。
3. 子结果可能是同步结果、异步终态结果或历史 artifact 恢复结果，均按同一 Result Envelope 读取。
4. 子结果的完整原始数据仍由各自 artifact/evidence 提供，Composite 只保存有界摘要和安全引用。

## 输入契约

版本：`spatial-agent.composite-request.v1`

```json
{
  "schema_version": "spatial-agent.composite-request.v1",
  "request": "同时查看区域空间条件与经济指标趋势",
  "components": [
    {
      "component_id": "space",
      "domain_id": "gis",
      "request": "查询区域边界与栅格概况",
      "planner": "rule",
      "backend": "local",
      "required": true,
      "depends_on": []
    },
    {
      "component_id": "economy",
      "domain_id": "economic",
      "request": "查询指定区域 GDP 年度趋势",
      "planner": "rule",
      "backend": "memory",
      "required": true,
      "depends_on": []
    }
  ]
}
```

约束：组件最多 8 个；`component_id` 唯一且为有界标识；Domain、planner、backend 和请求文本均有长度上限；依赖必须引用已存在组件且不能形成环；不接受 Python 路径、工具名列表或任意文件路径作为路由依据。

## 输出契约

Composite 结果仍是公共 `spatial-agent.result-envelope.v1`，`type` 为 `composite_result`，并声明：

- `data_profile.primary = composite`；`kinds` 为 `composite` 加子结果的有序并集。
- `composite.schema_version = spatial-agent.composite-result.v1`。
- `composite.components` 只保留组件身份、Domain、状态、结果类型、data profile、回答摘要、失败/降级摘要、artifact/evidence 安全引用和 View 引用。
- 所有子组件失败、澄清、等待确认或数据不可用状态都可被表达；聚合状态为 `completed`、`partial`、`blocked` 或 `failed`。
- `result.views` 包含一个领域中立 Composite 面板，并将子结果已有 View 以组件前缀隔离后复用；前端只依赖 View/renderer，不依赖工具名或 Domain 分支。

## 证据契约

版本：`spatial-agent.composite-evidence.v1`。

证据至少包含组件计数、完成/失败/阻塞组件、每个组件的 evidence registry 可用性、降级状态、artifact 引用和聚合状态。缺失或非法子结果必须形成结构化 `component_result_unavailable`，不能静默丢弃。

## Commands

- Docker 精简回归：`docker compose --env-file .env.production run --rm app python -m unittest tests.test_m275_composite_contract -v`
- Docker compile：`docker compose --env-file .env.production run --rm app python -m compileall -q agent domains result_contract.py`
- Docker architecture：`docker compose --env-file .env.production run --rm app python scripts/architecture_check.py --strict`

## Project Structure

- `agent/composite_contract.py`：请求规范化、结果/证据聚合和公共 View 投影。
- `agent/nested_schema.py`：在公共 Result 边界接入 Composite 嵌套校验。
- `agent/contract_versions.py`、`agent/evidence_registry.py`：版本与证据 schema 登记。
- `tests/test_m275_composite_contract.py`：精简契约与失败/恢复投影测试。

## Code Style

Composite 模块只接收 `Mapping`/标准 Result，不导入 `domains.gis` 或 `domains.economic`。所有列表、字符串和递归值都必须有界；跨域语义通过 `domain_id` 和结果契约传递，不通过工具名判断。

## Testing Strategy

- 单元/契约：输入 schema、依赖环、数据形态并集、部分失败、子 View 隔离和 evidence registry。
- Docker 集成：使用合成子结果验证公共 envelope；不依赖私有数据、不调用真实模型。
- 真实 GIS/Economic/live/浏览器：M275 不宣称完成，后续阶段显式验收。

## Boundaries

- Always：先验证组件身份和依赖；聚合结果保留失败与降级证据；不泄露路径和模型原文。
- Ask first：改变已有 Result Envelope、artifact 持久化格式或 HTTP 路由语义。
- Never：新增固定区域/固定问句分支；绕过 ToolRegistry/Domain Catalog；静默忽略失败组件。

## Success Criteria

1. 合法的跨 Domain 组件输入可被规范化，并拒绝重复 ID、未知依赖和循环依赖。
2. GIS/vector/raster 与 Economic/metrics/timeseries/document_evidence 子结果能生成统一 `composite_result`，data profile 和组件顺序稳定。
3. 子结果部分失败时 Composite 仍返回明确状态和可读 evidence，而非伪造完整成功。
4. 同一 Composite 结果经过公共 nested schema 校验后仍保持安全引用、View 和 evidence registry。
5. 公共代码不导入任何领域包，Docker 精简契约、compileall 和 architecture strict 通过。

## Non-goals

M275 不实现开放式跨域 LLM Planner、跨域异步 worker、Composite artifact 持久化或 HTTP endpoint；这些能力必须复用本 Spec 的契约并在后续 Spec 中单独验收。
