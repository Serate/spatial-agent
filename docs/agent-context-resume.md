# Agent 唯一恢复卡

新对话或上下文压缩后只执行 `pwsh -NoProfile -File scripts/resume_context.ps1`。不要默认读取其他恢复文档、问题日志、milestones、归档、完整测试或模型响应。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前状态

- M228 已完成：pre-run routing child + receipt 在 SQLite 原子提交并可跨 worker/重启回放；Journey Harness 贯穿 Application、HTTP、artifact 和 restart；legacy 前端 selection 活动路径已删除。
- M229 已实现并完成验收：Planner 输入投影与完整 source evidence 分离；async-first auto-domain live 验收只提交一个 run；GIS 后端初始化不可用时进入统一 recoverable lifecycle。
- M230 全局审计完成：CLI/HTTP/async/artifact/SQLite/重启、Text Domain、能力澄清、repair lineage、未对齐 gate、真实 DeepSeek + local GIS 和真实 run Console 动态展示均有证据。
- M231 已完成：使用 `ui-ux-pro-max` 固化 `design-system/spatial-agent-console/MASTER.md`；控制台完成紫/粉品牌 token、玻璃层级、紧凑对话输入、动态结果空态、可访问焦点和 reduced-motion 收口；Docker 生产镜像、9 项精简契约、前端 smoke 和 HTTP 200 验证通过。
- M232 已完成：控制台改为用户优先的信息层级，主视图突出分析结论、结构化结果和空间结果，规划指标、计划、证据、血缘和轨迹折叠到“查看执行详情”；Leaflet 地图增加 OSM/纯矢量底图切换、瓦片失败回退、比例尺、适合视图、图层图例、悬浮名称、属性弹窗、选中反馈和栅格范围视觉化。
- 最新生产镜像 healthy；聚焦回归 23/23、quick/stage/smoke、compileall 和 M230 显式浏览器验收通过；M231 的 Browser 控制进程初始化异常已单独记录。

## 下一步

当前 Goal 的 Runtime 验收标准和 M232 控制台用户体验阶段均已闭环；浏览器控制运行时本轮初始化异常退出、CDP `9222` 不可用，已记录为环境问题，后续恢复浏览器后只需补做视觉验收。继续扩展应创建新的 Goal，不在恢复时重新扫描历史文档。

## 不变量

- Runtime 领域中立；能力通过 facts/catalog/schema/workflow/result/view 扩展，不写区域或固定问句分支。
- Python 测试和 compileall 只在 Docker；Docker compose 必须显式使用 `--env-file .env.production`；默认门禁离线精简。
- 不读取、输出或提交密钥、`.env.production`、模型原文、真实原始数据或私有路径。

## 读取预算

- 恢复只加载本卡；源码先用 `rg -n -m 5` 定位，首轮最多读 2 个源码和 1 个测试文件。
- 仅有具体缺口时运行 `scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8` 或 `-Diagnostics`。
- 本卡超过 2KB 时立即压缩。
