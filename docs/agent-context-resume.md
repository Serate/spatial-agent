# Agent 上下文恢复入口

这是新对话或上下文压缩后的短入口，不是历史档案。

## 默认动作

1. 只读 [`agent-context-current.md`](agent-context-current.md)。
2. 执行 `git status --short --branch` 和 `git log -1 --oneline --decorate`。
3. 只根据当前任务定位源码；默认不读取历史文档、完整日志、模型响应、GeoJSON、私有路径或密钥。

## 需要历史时

先用有界检索，不要全文打开档案：

```powershell
pwsh -NoProfile -File scripts/resume_context.ps1 `
  -Topic "M220-B2|composition|evidence" `
  -MaxMatches 4 `
  -ContextLines 8
```

历史原文在 `docs/archive/context-history/`，仅用于按阶段或关键词审计。

## 当前约束

- Python、compileall、阶段测试默认通过 Docker。
- 默认测试离线、精简；真实模型、真实 GIS、浏览器和 live 网络只显式验收。
- 共享 schema、Runtime 状态和 Result/Evidence 契约按依赖顺序集成。
- 每阶段遵循“全局规划 → 实现 → 精简集成测试 → 更新短快照 → 提交推送 → 全局重规划”。

当前阶段、阻塞项、最近证据和下一步以 `docs/agent-context-current.md` 为准。
