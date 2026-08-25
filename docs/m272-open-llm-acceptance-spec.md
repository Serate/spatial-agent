# M272 Spec：开放式 LLM 多步验收

## 目标

验证真实 LLM 在已有能力目录和工具 schema 约束下，能够从开放式空间请求生成合法 TaskPlan，执行多步工具 DAG，并在 memory 与 local GIS 两种后端保持同一结果契约。验收必须把 provider timeout、harness deadline、Planner 失败和 GIS 工具失败分开归类。

## 范围

- 复用 M270 bounded live baseline、M271 provider probe 和现有 `LLMPlanner → Runtime → ToolRegistry → Domain` 链路。
- 使用一个真实空间总览 case 作为精简纵向验收，不为该问句增加专用分支。
- 先验证 memory backend 的真实模型计划，再验证 local GIS backend 的真实模型计划与真实数据执行。
- 输出只保留 case 状态、步骤/工具摘要、结果类型、metrics 和 error taxonomy；不保存 prompt、模型原文或完整工具参数。

## 非目标

- 不把一次成功当作所有开放式问题都已覆盖；复杂约束、跨领域 composite 和失败修复另行抽样。
- 不因为单次中转 timeout 修改 GIS 算法、Runtime 生命周期、ToolRegistry 或 Planner prompt。
- 不在默认 CI/quick/stage 中启用网络或私有数据。

## 验收

1. provider probe READY 后，真实 LLM + memory 的空间总览完成，结果/工具/evidence 契约通过。
2. 真实 LLM + local GIS 的同一空间总览完成，至少包含多步工具 DAG、真实数据执行和可读结果状态。
3. 真实 local GIS + Rule Planner 对照完成，证明数据/算法链路独立可用。
4. provider 在自己的 timeout 内失败时，事件为已完成但 `status=FAILED`；只有 harness deadline receipt 才产生 `event=timeout`。
5. prompt/schema 投影大小、provider 状态和 latency 可记录，但不泄露 prompt、key、模型原文或路径。
