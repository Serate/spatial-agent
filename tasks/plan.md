# 当前总计划：通用 Agent Runtime 与开放请求能力

> 本文件只保留当前总计划，不保存已完成阶段的详细过程。历史版本见
> `docs/archive/task-plans/plan-history.md`；阶段细节见 `docs/stages/` 或文档索引。

## 总目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime。真实模型默认使用受控 ReAct，
能够从开放式请求完成能力发现、计划、校验、工具执行、证据汇总和流式回答；GIS 只是业务载体。

## 阶段任务

1. [x] M318：契约、配置、基线和交接记录。
2. [x] M319：通用 Execution Policy，解除 workflow 强绑定。
3. [x] M320：真实模型默认 full ReAct。
4. [x] M321：默认开启的白名单网络搜索。
5. [x] M322：默认开启的沙箱 Python 工具提案。
6. [x] M323：人工审批、持久化和 Registry 治理。
7. [x] M324：approved 工具重启再绑定、治理投影和 Console 可见化。
8. [x] M325：Docker、真实模型、GIS、白名单搜索和 ReAct 纵向验收与版本交付。
9. [x] M326：开放式 ReAct 多步稳定性、部分结果表达与跨入口一致性交付。
10. [x] M327：开放请求能力发现、选择解释与跨类型结果质量。
11. [x] M328：受控开放行动、Web evidence、工具提案审批恢复与真实验收。
12. [x] M329：通用请求路由与跨域能力汇聚。
13. [x] M330：通用 Agent 开放问题质量与纵向行为验收。
14. [ ] M331：真实模型开放任务可靠性与通用能力可用率。

## 阶段循环

全局规划 → capability map → Spec → Plan → 实现 → 最小必要验证 → 更新交接 → 全局重规划 → 提交推送。

阶段任务应覆盖完整能力链；测试按独立失败模式合并，默认只运行受影响的紧凑测试、必要 smoke
和阶段验收。真实模型、真实 GIS、网络和 Docker 只走显式验收路径，不进入默认离线 CI。

## 当前阶段：M331（规划中）

M330 已完成通用开放问题的直接回答、能力发现、受控行动、降级恢复和跨入口体验验收。M331 从全局目标提高真实模型在
开放任务中的计划可靠性、工具组合可用率、答案质量和可观测反馈，不把工作退化为单一数据集适配；详细文件见 `docs/stages/M331/`。

## 文档入口

- 默认恢复：`docs/agent-work-state.md`
- 文档索引：`docs/document-index.json` 和 `docs/README.md`
- 源码索引：`docs/code-index.json` 和 `docs/code-index-overrides.json`
- 当前状态：`tasks/current-state.md`
- 历史账本：`tasks/task-progress.md`
- 当前阶段包：`docs/stages/M331/`
