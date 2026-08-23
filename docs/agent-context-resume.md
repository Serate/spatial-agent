# Agent 唯一恢复卡

新对话或上下文压缩后只执行 `pwsh -NoProfile -File scripts/resume_context.ps1`。不要默认读取其他恢复文档、问题日志、milestones、归档、完整测试或模型响应。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前状态

- M228 已完成：pre-run routing child + receipt 在 SQLite 原子提交并可跨 worker/重启回放；Journey Harness 贯穿 Application、HTTP、artifact 和 restart；legacy 前端 selection 活动路径已删除。
- 最新生产镜像 healthy；聚焦回归 31/31、quick/smoke、compileall 和领域/能力/确认三条 canonical 浏览器验收通过。

## 下一步

启动 M229：用真实模型 + 真实 GIS/Docker 完成复杂开放请求纵向验收和结构化能力缺口/降级闭环，再按完整 Goal 做全局审计。

## 不变量

- Runtime 领域中立；能力通过 facts/catalog/schema/workflow/result/view 扩展，不写区域或固定问句分支。
- Python 测试和 compileall 只在 Docker；Docker compose 必须显式使用 `--env-file .env.production`；默认门禁离线精简。
- 不读取、输出或提交密钥、`.env.production`、模型原文、真实原始数据或私有路径。

## 读取预算

- 恢复只加载本卡；源码先用 `rg -n -m 5` 定位，首轮最多读 2 个源码和 1 个测试文件。
- 仅有具体缺口时运行 `scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8` 或 `-Diagnostics`。
- 本卡超过 2KB 时立即压缩。
