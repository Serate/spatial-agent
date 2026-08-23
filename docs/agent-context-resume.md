# Agent 上下文恢复入口

本文件只说明恢复动作，不保存阶段历史。

新对话或上下文压缩后执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

该命令只输出 `docs/agent-context-current.md`、Git 状态和最近提交。不要再默认读取 `docs/task-resume.md`、`docs/agent-development-issues.md`、`docs/milestones.md` 或归档目录；它们只在当前卡明确要求或用户给出阶段/关键词时按需读取。

按需追溯历史：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "M220|evidence" -MaxMatches 4 -ContextLines 8
```

源码阅读也采用预算：先 `rg -n -m 5` 定位，再读取命中附近不超过 40 行；默认最多 2 个源码文件和 1 个测试文件。当前目标、阻塞项和下一步以 `docs/agent-context-current.md` 为准。
