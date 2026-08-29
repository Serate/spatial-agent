# 当前总计划：M318-M326 受控开放 Agent Runtime

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
10. [ ] M327：开放请求能力发现、选择解释与跨类型结果质量。

## 阶段循环

全局规划 → capability map → Spec → Plan → 实现 → 最小必要验证 → 更新交接 → 全局重规划 → 提交推送。

阶段任务应覆盖完整能力链；测试按独立失败模式合并，默认只运行受影响的紧凑测试、必要 smoke
和阶段验收。真实模型、真实 GIS、网络和 Docker 只走显式验收路径，不进入默认离线 CI。

## 当前阶段：M327（规划完成）

M326 已在真实模型、Docker/GIS、白名单搜索、SSE、artifact、轮询和重启恢复上完成最小纵向验收，
并完成开放 ReAct 增量动作、部分结果和 Artifact 原子发布收口。M327 从产品、Runtime、Domain、
数据、模型、部署、体验和测试七个维度补齐通用能力描述、选择解释和跨类型结果摘要；详细文件见
`docs/stages/M327/`。

## 文档入口

- 默认恢复：`docs/agent-work-state.md`
- 文档索引：`docs/document-index.json` 和 `docs/README.md`
- 源码索引：`docs/code-index.json` 和 `docs/code-index-overrides.json`
- 当前状态：`tasks/current-state.md`
- 历史账本：`tasks/task-progress.md`
- 当前阶段包：`docs/stages/M327/`
