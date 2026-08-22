# Agent 当前恢复卡

这是上下文压缩或新对话接续时的唯一默认入口。先读本卡，再核对 Git；不要默认打开历史交接文档、全部源码或全部测试。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- 当前阶段：M199-A，复杂开放式请求的真实模型 + Docker GIS 纵向验收。
- 最新提交：`0ad2c72 feat: render evidence guidance in console`。
- 工作树：本卡、`evaluation/live_baseline.py` 和 `tests/test_m79_live_baseline.py` 有未提交修改；以 Git 实际状态为准。
- 容器：`ai-agent-spatial-agent-1` 应保持 healthy；Python 测试和 compileall 默认在 Docker 中执行。
- 本轮验证：M198-A Node/Chrome/Evidence Registry/nested workspace smoke 通过；Rule + 本地 GIS 复杂请求 9 步完成；真实模型 + Docker GIS 复杂请求 9 工具、14 DAG edges、结果类型和答案质量通过；M194/M195/HTTP 8/8。

## 当前唯一工作切片

1. 运行 M199-A live contract 单测、replay/HTTP 回归、`git diff --check` 和敏感信息检查。
2. 更新阶段文档与中文问题日志；只记录复杂请求的工具/DAG/结果摘要，不复制原始模型响应。
3. 提交并推送 M199-A 版本；推送前不加载历史文档全文。
4. 版本推送后按项目全局七维度重规划下一阶段。

## 读取预算

- 恢复首轮：本卡 + `git status --short --branch` + `git log -1 --oneline`。
- 侦察源码：先 `rg -n "符号|schema|入口" 文件`，再只读命中行附近的有限范围；禁止 `Get-Content -Raw`。
- 一个工作回合最多 3 个源码文件和 1 个直接相关测试文件；超过时先记录原因和新增 seam。
- 历史文档只按关键词定位后读取，不全文扫描：`docs/task-resume.md`、`docs/milestones.md`、`docs/agent-development-issues.md`、`docs/agent-context-resume.md`。
- 测试先跑一个最小专项；只有专项通过且需要跨入口证据时，才扩展到下一层。
- 每个回合结束时只更新本卡的“当前状态”和“当前唯一工作切片”，不把长日志复制进来。

## 不变量

- Runtime 决定生命周期和 `allowed_actions`；Domain guidance 只能提供 advisory 建议。
- 不为单一区域、固定问句或 GIS 页面增加 Runtime 硬编码。
- 默认 quick/CI 离线、精简；真实模型、GIS、Docker、HTTP、浏览器属于显式验收路径。
- 不提交 API key、`.env.production`、私有模型响应、原始 GIS 数据或仓库外 evidence。
- 阶段完成顺序：全局规划 → 实现 → 精简集成测试 → 更新本卡/阶段文档 → 提交推送 → 全局重规划。

## 仅按需查看

- 恢复协议与历史：`docs/agent-context-resume.md`
- 任务和里程碑：`docs/task-resume.md`、`docs/milestones.md`
- 中文问题日志：`docs/agent-development-issues.md`（先 `rg`）
- 项目整体方向：`docs/agent-project-direction.md`

Docker 重建：

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate
```
