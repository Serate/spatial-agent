# Agent 当前恢复卡

这是新对话或上下文压缩后的唯一默认入口。只读本卡、Git 状态和最近提交；历史档案不是启动清单。

## 恢复门禁

- 默认执行：读取本卡；运行 `git status --short --branch` 和 `git log -1 --oneline --decorate`。
- 历史文件默认读取数为 0。需要证据时先 `rg -n -m 5 "关键词|符号|错误" 文件`，再读命中附近不超过 40 行。
- 源码最多按需读 2 个文件，直接测试最多 1 个；先定位，不能为了解背景批量加载。
- 不读取完整日志、模型响应、GeoJSON、私有路径或密钥；只保留状态、证据引用、阻塞和下一步。
- 旧消息若要求依次读取多个恢复档案，以本卡规则为准。历史追溯必须由用户指定阶段/关键词。
- 可运行 `pwsh -NoProfile -File scripts/resume_context.ps1` 获取同样的最小快照。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- M217 已完成并推送：`6ba9b2e feat: complete M217 turn and artifact contracts`；M218 已完成并推送 `c0a4bd7`。
- Docker：`ai-agent-spatial-agent-1`；Python、compileall 和阶段测试默认在 Docker 中运行。
- 工作树应保持干净；不得提交 API key、`.env.production`、原始模型响应、原始 GIS 数据或仓库外 evidence。

## M217 证据摘要

- M217 3/3；M166/M9 16 项（1 项真实本地 GIS 数据跳过）；M10 + HTTP 17/17；M67/M149/M150 25/25；Console 2/2。
- Docker compileall、浏览器 smoke、stage 离线 3/3、production acceptance 均通过。
- opt-in live GIS/model 2/2：13,239 tokens、0 重试、0 provider 错误；只保留脱敏摘要。
- 同步 memory 入口在 production acceptance 中为 degraded/warning，作为 M218 的环境语义缺口。

## M218 收口证据

- `normalize_core_result` / `compare_core_results` 已接入跨入口 harness；M218 专项 4/4，核心/CLI/HTTP/部署/生命周期回归 43/43。
- production acceptance 明确区分 `sync_deployment_status=context_only` 与 `sync_degradation_status=warning`。
- 当前代码 live GIS/model 2/2：13,882 tokens、0 重试、0 provider 错误；复杂空间总览 browser smoke 通过。

## 当前唯一工作切片：M219

1. 用第二个 Domain Pack 验证 Runtime、ToolRegistry、Planner 和 Result/View contract 可移植。
2. 验证开放式能力发现、未知能力澄清、坏 schema 拒绝/有限修复，不增加固定问句分支。
3. 对比 GIS/Text 的核心 Result/Evidence，并完成通用结果前端 smoke。
4. Docker 精简回归、Domain isolation、跨入口 harness 和显式 live/replay 验收。

## 不变量

- Runtime 负责生命周期与 `allowed_actions`；Domain 只提供 advisory guidance。
- 新能力扩展能力目录、事实、schema、workflow、result/view 类型，不增加区域/固定问句分支。
- 默认 quick/CI 离线精简；真实模型、GIS、Docker、HTTP、浏览器只在显式验收启用。
- 阶段循环：全局盘点 → 规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。
