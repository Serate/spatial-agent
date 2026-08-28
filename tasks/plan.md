# 当前总计划：M318-M325 受控开放 Agent Runtime

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
6. [ ] M323：人工审批、持久化和 Registry 治理。
7. [ ] M324：前端、SSE、恢复和双 HTTP 入口整合。
8. [ ] M325：Docker、真实模型、GIS、搜索验收与版本交付。

## 阶段循环

全局规划 → capability map → Spec → Plan → 实现 → 最小必要验证 → 更新交接 → 全局重规划 → 提交推送。

阶段任务应覆盖完整能力链；测试按独立失败模式合并，默认只运行受影响的紧凑测试、必要 smoke
和阶段验收。真实模型、真实 GIS、网络和 Docker 只走显式验收路径，不进入默认离线 CI。

## 文档入口

- 默认恢复：`docs/agent-work-state.md`
- 文档索引：`docs/document-index.json` 和 `docs/README.md`
- 源码索引：`docs/code-index.json` 和 `docs/code-index-overrides.json`
- 当前状态：`tasks/current-state.md`
- 历史账本：`tasks/task-progress.md`
- 当前阶段包：`docs/stages/M323/`
