# M311 通用分析意图与跨域开放链路实施计划

## A：冻结分析意图契约

- 定义 `analysis-intent.v1` 的操作、数据类型、依赖、事实引用、置信/澄清和版本字段。
- 复用现有 `data_kinds` 与 RequestFacts，不引入第二套结果或授权语义。
- 覆盖空值、未知操作、冲突别名、重复操作和超限输入。

## B：接入 Planner Envelope 与能力目录

- 将意图摘要、操作候选、数据类型候选和能力候选加入现有安全 Planner Envelope。
- 让模型只选择目录中的 capability、workflow、result type；所有 provider 输出继续经过
  schema、canonical plan 和 Domain resolver 校验。
- 让 Rule/Replay 适配同一契约，作为离线回归而非模型替代。

## C：闭合跨域操作链路

- 复用现有 GIS 的 record/spatial 能力和 Economic 的 query/trend/compare/evidence 能力。
- 处理操作之间的依赖、数据类型兼容、字段/时间/空间事实缺口和不可用状态。
- 保持未验证计划不创建 execution run，并保留 repair/failure lineage。

## D：结果、证据与前端投影

- 让 Result/View/Evidence 按意图和数据类型动态呈现，不按工具名或 Domain 分支。
- 对未知/澄清/部分完成结果提供用户可读摘要、限制、证据和下一步。
- 对照同步、异步、HTTP、artifact、SQLite/restart 的公共 identity。

## E：阶段验收与交付

- Docker 运行 M311 契约、必要相邻回归、compileall、architecture strict、Node projection、
  Service/readiness 和真实本地 GIS 验收。
- 离线门禁通过后最多一次真实模型验收；不保存模型原文、密钥或完整原始数据。
- 更新中文问题日志、milestones、工作快照和任务账本，提交并推送版本。

## 顺序与并发

`A → B → C → D → E`；当前 goal 约束为串行实施，不拆出并行分支。

## 风险与缓解

- 意图变成第二套 Planner：只允许作为 Planner Envelope 中的版本化输入摘要，canonical plan
  仍是唯一执行权威。
- 模型输出自由发明操作：使用枚举、目录候选和 fail-closed 校验。
- 组合链路扩大 Token：使用有界摘要、候选上限和固定 envelope budget。
- 为了验收重新增加专题分支：只使用现有 GIS/Economic 能力，新增测试必须以通用操作为主。

## 实施结果

- A～C 已完成：`analysis-intent.v1` 已接入 Domain-owned facts、Capability Catalog、
  Planner Envelope、Composite Planner 校验和现有执行闭合；未知操作、依赖环、未声明
  capability operation 和不完整结果类型均 fail closed。
- D 已完成：Composite View、异步/artifact evidence 和 Console projection 统一保留
  归一化意图与 data kinds，并以通用用户文案展示，不新增领域页面分支。
- E 已完成：Docker 精简契约、相邻回归、compileall、architecture strict、Service、
  跨入口 identity、真实本地 GIS HTTP 和 readiness 均通过；阶段唯一真实模型验收按
  实际 provider/执行结果记录。
- 阶段收口时额外修复了正常 LLM 计划缺少 `output.type` 导致顶层 Result 为 `unknown` 的
  问题；不从工具名称猜测结果类型，保持公共 Result Contract 的权威性。
