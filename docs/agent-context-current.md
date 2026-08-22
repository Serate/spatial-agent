# Agent 当前恢复卡

这是上下文压缩或新对话接续时的唯一默认入口。恢复首轮不要自动打开其他文档、源码、测试、完整日志或模型响应。

## 恢复门禁

1. 只读本文件，然后执行 `git status --short --branch` 和 `git log -1 --oneline --decorate`。
2. 先确定一个“当前唯一工作切片”，再查资料；不要为了了解全局全文扫描历史。
3. 查找使用 `rg -n -m 5 "关键词|符号|错误" 文件`，命中后只读取附近有限行，例如：
   `Get-Content 文件 | Select-Object -Skip 120 -First 60`。
4. 每个回合最多读取 1 个历史文件的 1 个命中区间（默认不超过 80 行）、3 个源码文件和 1 个直接相关测试文件。超过时先说明原因。
5. 只保留状态、提交、证据引用、阻塞项和下一步；测试输出、原始模型响应和大文件内容只保留摘要或路径。

历史档案 `docs/agent-context-resume.md`、`docs/task-resume.md`、`docs/milestones.md`、
`docs/agent-development-issues.md` 均按需查询，不是恢复入口；必须先精确定位，再读取命中段。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- 当前阶段：M210-A 已完成，Action receipt 与 transition evidence 贯通 Artifact 待推送。
- 最近功能提交：`4dfe49c feat: expose repair lineage in evidence projection`。
- 容器：`ai-agent-spatial-agent-1` 应保持 healthy；Python 测试和 compileall 默认在 Docker 中执行。
- 已通过：M200–M205 的跨入口、恢复、证据、Node/Chrome/DOM smoke 及生产 acceptance。
- 当前无阻塞：M206 地图清理、M207 preview、M208 lifecycle、M209 repair lineage 和 M210 receipt 回归均已通过。

## 当前唯一工作切片

1. 复核 M210-A 的最小 diff、敏感信息和文档摘要。
2. 提交并推送 M210-A；保留 Docker/HTTP/Artifact 验收证据引用，不提交原始响应。
3. 推送后按全局七个维度规划 M211，再选择一个 action failure/idempotency/restart 纵向切片实现。

## 不变量

- Runtime 决定生命周期和 `allowed_actions`；Domain guidance 只能提供 advisory 建议。
- 不为单一区域、固定问句或 GIS 页面增加 Runtime 硬编码。
- 默认 quick/CI 离线、精简；真实模型、GIS、Docker、HTTP、浏览器属于显式验收路径。
- 不提交 API key、`.env.production`、私有模型响应、原始 GIS 数据或仓库外 evidence。
- 阶段完成顺序：全局规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。

## 按需入口

- 项目方向：`docs/agent-project-direction.md`
- 阶段历史：`docs/task-resume.md` 或 `docs/milestones.md`（先 `rg`）
- 中文问题日志：`docs/agent-development-issues.md`（先按错误关键词 `rg`）
- 恢复历史：`docs/agent-context-resume.md`（仅需追溯时读取）

Docker 重建：

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate
```
