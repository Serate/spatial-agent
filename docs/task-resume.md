# 当前任务恢复指针

本文件不是启动文件，也不保存当前状态。新对话或上下文压缩后只执行：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1
```

当前状态只维护在 [`agent-context-current.md`](agent-context-current.md)。本文件仅在恢复卡明确指向任务历史时按需读取；详细历史位于 `docs/archive/context-history/task-resume-history.md`，不得全文加载。
