# Agent 唯一恢复卡

新对话或上下文压缩后只执行 `pwsh -NoProfile -File scripts/resume_context.ps1`。不要默认读取其他恢复文档、问题日志、milestones、归档、完整测试或模型响应。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前状态

- M225 已完成：有界跨 Domain discovery、Catalog/Model/fallback Selector、共享 `DomainRoutingApplication`、版本化澄清/改选、SQLite lineage/binding/restart 和 Console 智能选择均已落地。
- 生产镜像 healthy；M225 14/14、M224 17/17、quick/smoke、compileall 和三条浏览器验收通过。

## 下一步

提交推送 M225；M226 将 routing identity/lineage 收敛进 Result、async、artifact、restart evidence，并补受控 Model Selector 与跨入口 Harness。

## 不变量

- Runtime 领域中立；能力通过 facts/catalog/schema/workflow/result/view 扩展，不写区域或固定问句分支。
- Python 测试和 compileall 只在 Docker；默认门禁离线精简，live/GIS/browser 仅显式验收。
- 不读取、输出或提交密钥、`.env.production`、模型原文、真实原始数据或私有路径。

## 读取预算

- 恢复只加载本卡；源码先用 `rg -n -m 5` 定位，首轮最多读 2 个源码和 1 个测试文件。
- 仅有具体缺口时运行 `scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8` 或 `-Diagnostics`。
- 本卡超过 2KB 时立即压缩。
