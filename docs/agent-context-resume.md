# Agent 上下文恢复入口

本文件只说明恢复动作，不保存阶段历史。新对话或上下文压缩后只执行下面这一条命令；不要依次打开任务档案、问题日志和归档。

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

默认只输出短恢复卡。需要 Git 诊断或历史时显式使用：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 -Diagnostics
pwsh -NoProfile -File scripts/resume_context.ps1 -Topic "M220|evidence" -MaxMatches 4 -ContextLines 8
```

源码也按预算读取：先用 `rg -n -m 5` 定位，再只读命中附近窗口；默认最多 2 个源码文件和 1 个测试文件。目标、阻塞项和下一步以 `docs/agent-context-current.md` 为准。
