# Spec：M304 Provider-backed 规划可靠性与可恢复交互

## 目标

让真实模型参与的开放式规划具备清晰、统一、可恢复的生命周期：请求进入 provider 前可观测，provider 返回后经过结构化校验和 canonical 计划门禁；超时、澄清、拒绝、失败和执行状态在 CLI、HTTP、异步和 Console 中保持同一语义。

## 公共契约

1. `ProviderHealth`：配置是否完整、provider 是否可达、模型能力是否支持当前 structured-output 模式；只输出安全身份和状态。
2. `ProviderDeadlineReceipt`：harness/provider deadline、重试次数、是否超时、失败平面和 elapsed；不得包含请求密钥或模型原文。
3. `PlannerOutcome`：`PLANNED`、`NEEDS_CLARIFICATION`、`REJECTED`、`FAILED`，分别携带可恢复动作；只有 `PLANNED` 进入 TaskPlan/binding。
4. `Composite Planner Evidence`：请求/上下文/计划指纹、候选和组件数量、provider 状态摘要；不保存完整 provider payload。
5. `Lifecycle Projection`：活动规划返回 pending，终态返回最终 Result/View/Evidence；规划失败不得创建 execution run。

## 行为要求

- provider 调用使用现有 OpenAI-compatible seam；timeout、retry 和 max output token 都有显式上限。
- structured response 先做类型/schema 校验，再通过 canonical Composite request、DAG、TaskPlan、ToolRegistry 和 execution binding；任何不确定字段 fail closed。
- 事实缺失、能力不可用、provider timeout、计划拒绝和执行失败使用不同 reason/error/failure plane。
- 有限 repair 只能修复结构格式，不能改变 capability、domain、事实、权限、工具参数或执行结果；repair 失败保留 lineage。
- 前端只读取结构化状态、answer、View 和 evidence，显示用户可执行的“补充信息/稍后重试/查看结果”等动作。

## 验收矩阵

| 场景 | 预期 | 是否创建 run |
| --- | --- | --- |
| provider 快速返回合法计划 | `PLANNED`，进入既有执行链路 | 是，且必须通过 binding |
| 事实不足 | `NEEDS_CLARIFICATION`，给出缺口 | 否 |
| provider timeout/不可达 | `FAILED`，标记 provider/harness，可重试 | 否 |
| 结构化输出可有限修复 | 记录 repair lineage，重过全部门禁 | 仅修复后计划合法时 |
| 未知能力/非法 DAG | `REJECTED`，给出安全原因 | 否 |
| 已规划执行失败 | `FAILED/PARTIAL`，保留 Result/Evidence | 已创建的 run 按生命周期收口 |

## 非目标

本阶段不更换模型供应商、不在 CI 调用真实模型、不扩大 GIS/Economic 工具菜单、不引入 RAG，也不把单次 live 成功当作系统总体成功率。

## 阶段门禁

Docker 精简契约、相邻 Planner/Composite 回归、compileall、architecture strict、Node projection、Service smoke、生产 readiness 和一次显式 live 必须可独立报告；live 结果可为成功、澄清或 provider failure，但必须有脱敏 receipt。

## 阶段收口

M304-A～F 已完成。Docker 精简回归、compileall、architecture strict、Node projection、Service smoke、生产 HTTP 和 readiness 全部通过；唯一一次显式 live 使用 60 秒、0 重试，结果为 `FAILED/timeout`、`error_plane=harness`、未创建 execution run。该结果按 provider 延迟失败记录，不代表 GIS 执行失败，也不伪装成成功计划。
