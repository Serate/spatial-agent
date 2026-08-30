# M331 阶段交接

## 状态

- 阶段：`M331` 真实模型开放任务可靠性与通用能力可用率
- 状态：M331-0、M331-A～F 已完成，待提交阶段版本
- 基线：M330 阶段交付版本 `0ce3ba4`
- 协作：单 Agent，最大并发度 1；测试、真实模型和 GIS 优先使用 Docker

## 当前目标

提高真实模型在开放任务中的计划、工具组合、答案和恢复可用率。M330 已完成通用入口、直接回答、能力发现、受控行动、
SSE/Artifact 和真实纵向验收；M331 不新增固定问句分支，不引入 RAG，不扩大安全权限。

## M331-0 验收

- 已建立 `capability-map.md`、`spec.md`、`plan.md` 和本 handoff。
- 恢复入口已切换到 M331；默认只读取本文件、热状态和 M331 规划文件，不读取 M330 全量源码、模型输出或历史账本。

## 必要文件

- `docs/stages/M331/{capability-map.md,spec.md,plan.md,handoff.md}`
- `docs/agent-work-state.md`
- `tasks/current-state.md`
- `docs/document-index.json`

## 恢复规则

只读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本 handoff 和当前 Plan 子任务明确列出的源码/测试。模型原文、
Prompt、密钥、网页正文、工具源码、完整历史和全量测试按需读取，不作为默认上下文。

## M331-A 交接

- 已完成：M330 已提交并推送；代码/文档索引重新生成并通过校验。
- 已完成：建立脱敏 conformance 矩阵，覆盖 planner、ReAct decision、answer envelope 的字段漂移、截断 JSON、错误结果类型、
  漏字段、额外字段和 Provider timeout；新增共享 `agent/integration/structured_response.py`。
- 已完成：Planner、ReAct、普通答案和 Composite 答案使用统一的一次 compact recovery、无歧义字段修复和稳定错误分类；
  恢复响应不再递归重试，完整 schema/权限/结果校验仍由原有调用方负责。
- 验证：Docker M331-A 与相邻 M320/答案/M330 回归 `40/40` 通过；不保存模型原文、Prompt 或敏感配置。
- 约束：修复必须有界、可审计、不可绕过 schema/权限/结果 owner；不保存模型原文、Prompt、密钥或网页正文。

## M331-B 当前交接

- 已完成：能力目录、工具 owner、结果类型推导、依赖/权限/预算/preflight 和部分成功组合均保持公共闭合；新增通用任务组合矩阵。
- 已完成：验证直接回答、单域、多域和混合任务共享 General Runtime，不增加关键词路由；部分成功 fallback 会明确区分未完成项。
- 验证：Docker M331-A/B 与 M320、答案、Host、通用入口回归 `50/50` 通过。

## M331-C 当前交接

- 进行中：检查多轮/长任务上下文裁剪、预算耗尽、取消、重试、澄清续跑、审批恢复和重启回放的 identity 与终态一致性。
- 必要源码：`agent/context_engineering.py`、`agent/runtime_state.py`、`agent/sqlite_store.py`、`agent/artifact_store.py`、
  `agent/run_events.py`、`agent/application/async_runs.py` 及直接相关紧凑测试。
- 约束：上下文只保存有界安全历史，不保存 Prompt、模型原文、隐藏思维链、密钥或网页正文；事件回放不可重复消费。

## M331-D/E 当前交接

- 已完成：新增 `agent/answer_quality.py`，对最终可见答案执行领域无关的空值、长度、内部标记、乱码和状态披露检查；质量 receipt 进入 `answer_generation` 公共 evidence，模型答案和 Runtime fallback 均覆盖。
- 已完成：Python 与 Console RunEvent 契约补齐 `react_waiting_for_approval` 及 ReAct 事件可见性；答案流前端上限与 Runtime `answer_length` 统一为 6000 字符。
- 验证：Docker M331 结构化输出/任务组合/答案体验/上下文/答案流/事件/生成回归 `42/42`；Console answer/event/projection smoke、compileall、architecture strict、服务 smoke 通过。
- 真实模型：通用直答 `COMPLETED`、`live_model`、`streaming=True`、质量 `pass`；复杂 GIS 多步请求在 45 秒有界验收中未返回，归类 provider 规划延迟，未保存原文。
- 修改文件：`agent/answer_quality.py`、`agent/answer_generation.py`、`agent/runtime.py`、`agent/application/composite_runs.py`、`agent/run_events.py`、`agent/runtime_core/run_lifecycle.py`、`web/src/console_answer_stream.js`、`web/src/console_run_events.js` 及对应测试/文档。

## 阻塞与下一步

- 阻塞：无。
- M331-C 已完成：Docker 恢复紧凑回归 `24/24` 通过；上下文超预算时先压缩版本化 workflow template 摘要，保留 schema、能力边界和步骤形状。
- M331-F 已完成：热状态、任务账本、开发问题记录、代码索引和文档索引已更新；复杂 live provider 延迟作为下一阶段可靠性/性能输入，不扩大本阶段范围。
- 下一阶段建议：围绕真实模型复杂规划延迟与增量反馈，建立 planner/provider/execute/answer 的有界预算、心跳、可恢复超时和跨入口归因；保持通用 Runtime、Domain Pack、schema 和权限边界不变。
- 下一步：提交并推送 M331 阶段版本。
