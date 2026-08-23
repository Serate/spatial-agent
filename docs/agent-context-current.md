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
- M217 已完成并推送：`6ba9b2e feat: complete M217 turn and artifact contracts`。
- Docker：`ai-agent-spatial-agent-1`；Python、compileall 和阶段测试默认在 Docker 中运行。
- 工作树应保持干净；不得提交 API key、`.env.production`、原始模型响应、原始 GIS 数据或仓库外 evidence。

## M217 证据摘要

- M217 3/3；M166/M9 16 项（1 项真实本地 GIS 数据跳过）；M10 + HTTP 17/17；M67/M149/M150 25/25；Console 2/2。
- Docker compileall、浏览器 smoke、stage 离线 3/3、production acceptance 均通过。
- opt-in live GIS/model 2/2：13,239 tokens、0 重试、0 provider 错误；只保留脱敏摘要。
- 同步 memory 入口在 production acceptance 中为 degraded/warning，作为 M218 的环境语义缺口。

## 当前唯一工作切片：M218

开放式请求的纵向验收与通用结果/生命周期证据闭环：

1. 建立 CLI/HTTP/Async/Artifact/SQLite/Console 的核心 Result/Evidence 对比 harness。
2. 收敛 lifecycle、decision、selection interaction 和 readiness 的语义投影，保留 receipt/transport lineage 差异。
3. 用动态 Result/View/Answer contract 驱动复杂请求前端 smoke，不增加 GIS 页面分支。
4. 固化真实模型 + 真实 GIS/Docker 的脱敏短验收、token/延迟和错误分层。
5. Docker 精简 stage、HTTP contract、replay/repair 和浏览器 smoke 分层验收，完成后再次全局重规划。

## 不变量

- Runtime 负责生命周期与 `allowed_actions`；Domain 只提供 advisory guidance。
- 新能力扩展能力目录、事实、schema、workflow、result/view 类型，不增加区域/固定问句分支。
- 默认 quick/CI 离线精简；真实模型、GIS、Docker、HTTP、浏览器只在显式验收启用。
- 阶段循环：全局盘点 → 规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。
