# 当前任务恢复入口

本文件只提供短指针，不保存阶段历史。新对话或上下文压缩后不要全文读取本文件；请先读取 [`agent-context-current.md`](agent-context-current.md)。

## 当前任务

当前阶段、目标、验收证据和下一步统一维护在 [`agent-context-current.md`](agent-context-current.md)。阶段完成时只更新短快照，并将详细过程追加到归档或阶段记录。

## 按需追溯

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 `
  -Topic "阶段号|功能名|错误关键词" `
  -MaxMatches 4 `
  -ContextLines 8
```

详细历史位于 `docs/archive/context-history/task-resume-history.md`；不要直接全文加载。
