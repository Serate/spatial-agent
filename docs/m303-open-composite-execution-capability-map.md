# M303 开放式 LLM Composite 执行成功链路能力图

## 全局定位

M302 已经把 Planner 的阶段投影、执行身份以及 Result/View/Evidence 的跨入口一致性收口。当前真正影响产品“像 Agent”的缺口，是真实模型虽然能够访问已注册能力，但还没有稳定地把开放式请求转成合法的多组件 TaskPlan/DAG，并进入 GIS/Economic 的真实执行链路。

M303 只解决这条纵向成功链路，不重写 Runtime、生命周期、ToolRegistry 或 Domain Pack，不把某个地区、问句或数据集写成专用流程。所有模型输出仍必须经过现有 catalog、workflow、TaskPlan、schema、binding 和结果契约门禁。

## 能力模块与依赖

| 模块 ID | 责任 | 依赖 |
| --- | --- | --- |
| `planner-decision-contract` | 明确模型在 discovery/selection 阶段如何从候选能力中选择组件、表达依赖和请求澄清 | M302 Planner Envelope |
| `canonical-plan-adapter` | 将结构化模型输出安全规范化为 Composite 请求与组件 DAG，拒绝未知能力、空计划、身份漂移和越权字段 | `planner-decision-contract`、现有 Composite Planner |
| `execution-readiness-acceptance` | 用 Replay/Rule 与真实目录验证 canonical plan 能通过 workflow、ToolRegistry、TaskPlan 和 execution binding | `canonical-plan-adapter` |
| `cross-entry-result-acceptance` | 对同一合法计划验证 sync、async、artifact、SQLite/restart、View/Evidence 的 identity 一致 | `execution-readiness-acceptance`、M278 生命周期 |
| `live-provider-delivery` | 执行一次有界真实模型 + Docker GIS/Economic 验收，区分成功、澄清、provider failure 和执行失败 | `cross-entry-result-acceptance` |
| `global-review-delivery` | 更新中文记忆、问题日志、版本和七维度全局重规划 | 全部模块 |

## 构建顺序

`planner-decision-contract` → `canonical-plan-adapter` → `execution-readiness-acceptance` → `cross-entry-result-acceptance` → `live-provider-delivery` → `global-review-delivery`

本阶段按串行方式实施。测试在阶段收口集中运行，不因每个模块重复执行同一套全量检查。

## 全局验收视角

- 产品：开放请求能够看到“发现能力—选择能力—执行—汇总”的真实阶段，而不是只看到固定模板摘要。
- 架构：模型输出只进入既有 Planner/TaskPlan/binding seam；公共 Runtime 不识别 GIS/Economic 专题。
- 数据：模型只能选择 catalog 中有 readiness、workflow 和 result profile 的能力；数据不足进入澄清或不可用状态。
- 模型：结构化输出错误、语义不完整、未知 identity 和空组件分别分类，最多使用既有有界 repair，不增加无界重试。
- 部署：Docker 是 Python/GIS/Node 验收环境；中转 provider 只在显式 live probe 中调用。
- 体验：答案引用结构化 Result/Evidence，技术身份不直接暴露给普通用户。
- 测试：保留最小 Replay/Rule 契约、一次跨入口验收和一次显式 live，默认 CI 不访问网络。

## 不在本阶段范围

- 不新增 RAG、开放互联网搜索、数据下载或自动修改数据。
- 不新增针对洪山区、武汉或某个固定自然语言表达的分支。
- 不通过放宽 schema、allowlist、workflow、ToolRegistry 或 binding 门禁制造模型成功。
- 不保存 API key、prompt、模型原文、私有路径或未脱敏真实原始数据。
