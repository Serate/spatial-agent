# Agent 当前恢复卡

这是上下文压缩或新对话接续时的唯一默认入口。先读本卡，再核对 Git；不要默认打开历史交接文档、全部源码或全部测试。

## 恢复协议（v2）

恢复上下文时只读取以下三项：

1. 本文件。
2. `git status --short --branch`。
3. `git log -1 --oneline --decorate`。

`docs/agent-context-resume.md`、`docs/task-resume.md`、`docs/milestones.md` 和
`docs/agent-development-issues.md` 都是按需查询的历史档案，不得在恢复首轮全文读取，
也不要为了查看目录执行 `rg '^#'` 之类的全文件扫描。历史追溯必须先用一个精确关键词定位，
再读取单个命中点附近的有限行，例如：

```powershell
rg -n -C 8 "M200|具体符号|错误关键词" docs/task-resume.md
rg -n -C 6 "错误关键词" docs/agent-development-issues.md
```

读取预算：每个工作回合最多读取 1 个历史文件、1 个命中区间（默认不超过 80 行）、3 个源码
文件和 1 个直接相关测试文件。超过预算时先说明新增 seam 或阻塞原因；不要用完整日志、原始
模型响应或大段测试输出填充当前上下文。阶段摘要只保留状态、提交、证据引用、阻塞项和下一步。

如果当前卡超过 80 行，应把旧状态移入历史档案，只保留最新阶段和当前唯一工作切片。当前卡
与 Git 实际状态冲突时，以工作树和提交为准，并在卡中修正，不追读整段历史来“对齐文字”。

## 当前状态

- 总目标：建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。
- 当前阶段：M202-A 已完成实现与 Docker 验收，待版本推送；下一阶段为 M203。
- 最新提交：`c7b83f5 fix: preserve lifecycle evidence in registry`。
- 工作树：M202-A 的 async projection 修复、精简回归、阶段记录和问题记录有未提交修改；后续实现以 Git 实际状态为准。
- 容器：`ai-agent-spatial-agent-1` 应保持 healthy；Python 测试和 compileall 默认在 Docker 中执行。
- 本轮验证：M198-A Node/Chrome/Evidence Registry/nested workspace smoke 通过；Rule + 本地 GIS 复杂请求 9 步完成；真实模型 + Docker GIS 复杂请求 9 工具、14 DAG edges、结果类型和答案质量通过；M200/M195/HTTP 跨入口专项 9/9；M201-A 专项 5/5、受影响回归 14/14；M202-A async/selection/recovery 8/8；容器 healthy。

## 当前唯一工作切片

1. 提交并推送 M202-A；推送前不加载历史文档全文。
2. 推送后按 M203 的七个全局维度统一 interaction envelope、Action Receipt 和 repair lineage。
3. 继续保持 Docker 测试、精简默认门禁和有界上下文恢复协议。

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
