# M331 阶段交接

## 状态

- 阶段：`M331` 真实模型开放任务可靠性与通用能力可用率
- 状态：M331-0 已完成，M331-A 尚未开始
- 基线：M330 阶段交付版本待确认
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

## 阻塞与下一步

- 阻塞：无。
- 下一步：M331-A，先建立真实模型结构化输出 conformance 场景矩阵，再决定最小公共解析/修复 seam。
