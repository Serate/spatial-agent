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
- M233 已完成：修复 Console 会话生命周期入口。自动领域未绑定时允许创建本地草稿会话并正确切换；新增带确认和失败汇总的“清空全部对话”；清空后重置消息、结果、地图 renderer、证据和会话状态；桌面顶部状态条压缩到约 79px，右侧对话工作区按视口保持约 675px 长度。补充会话与布局浏览器 smoke，Docker 重建后 5/5 契约测试和实际 smoke 通过。
- M234 已完成：修复真实“新建会话”点击无效。根因是 click Event 被误传为 `domainId`，事件绑定改为显式包装；新增固定 GIS 领域真实按钮点击 smoke，验证下拉从 1 增加到 2 且自动选中“对话2”。全量清理改为先获取目标、立即清空前端并创建空白会话，再执行旧会话删除；增加 session catalog generation 防止旧请求回填。Docker 6/6 契约测试、清空 smoke、固定领域点击 smoke 通过。
- M235 已完成：控制台首次使用默认组合改为“空间 GIS + 真实大模型 + 本地适配器”；保留已有领域 localStorage 选择。重新编排桌面布局为左侧结果工作区、右侧固定聊天列，聊天内部改用可伸缩消息区和固定底部输入区；修复聊天框因顶部状态卡占位与错误高度计算导致首屏看不到“发送”按钮的问题，预览与发送改为横向并列。Docker 生产镜像重建并保持 healthy。
- M236 已完成：进一步收紧桌面顶部“准备好执行任务”状态条，减少标题、说明和内边距占用；聊天列高度同步按收紧后的状态条重新计算，将释放的首屏空间交给消息区，保持输入底栏可见。Docker 页面已重建。
- M237 已完成：修正状态条的横向归属。桌面端“准备好执行任务”只占左侧分析结果列，右侧聊天从内容区顶部开始并跨越结果区两行；避免状态条横跨整页，同时进一步增加对话的可用高度。Docker 页面已重建。
- M238 已完成：修复桌面端“领域动作”展开层被聊天消息区遮挡的问题。弹出层提升设置栏层级，改为相对设置栏的自适应定位，限制最大高度并允许内部滚动；聊天容器不再裁剪必要的弹出内容。Docker 页面已重建。
- M239 已完成：修复综合 GIS 结果在 GeoJSON 摘要被截断时错误退回规则栅格矩形的问题。只要仍有 GeoJSON artifact，就继续绘制可用的部分真实几何；没有几何 artifact 时，地图改为虚线“栅格外接范围”，明确不代表有效像元覆盖。补充 result contract、GIS renderer 回归 smoke，Docker 定向验证通过。
- M240 已完成：新增独立 `agent.answer_generation` 回答生成边界。真实模型模式在工具执行完成后，把请求、目标和工具事实做有界脱敏投影，使用结构化输出生成面向用户的中文总结；schema、长度和内部引用校验失败时回退 Domain Composer。规则/离线模式不额外调用模型，并统一记录 `answer_generation` 有界证据；同步、异步、artifact 和 SQLite 恢复均保留该证据。Docker compileall、精简跨领域/结果契约/异步回归和前端 smoke 通过。
- M241 已完成：修复 M240 后 GitHub CI 的两条过时 `memory://` 断言，更新 `tests/test_dev_gate.py` 和 `scripts/smoke_check.py` 为用户回答契约；Docker 中 `python scripts/test_profile.py --profile ci` 的核心契约与 service smoke 均通过。
- 本地阶段提交已完成，当前 HEAD 为 `c0a2780`；此前 GitHub push 曾因宿主网络超时，现已恢复并成功推送到 `origin/main`，不要重复实现本阶段代码。
- 最新生产镜像 healthy；聚焦回归 23/23、quick/stage/smoke、compileall 和 M230 显式浏览器验收通过；M231 的 Browser 控制进程初始化异常已单独记录。

## 下一步

当前 Goal 的 Runtime 验收标准、M233 控制台会话/布局阶段和 M240 回答生成边界均已闭环；最终答案现在可由真实模型自然表达，并在不可用时安全回退。下一阶段应围绕真实模型 + 真实 GIS 的端到端验收、回答事实一致性评估和前端 answer-generation evidence 展示规划，不要继续扩展 GIS 专用模板分支。

## 不变量

- Runtime 领域中立；能力通过 facts/catalog/schema/workflow/result/view 扩展，不写区域或固定问句分支。
- Python 测试和 compileall 只在 Docker；Docker compose 必须显式使用 `--env-file .env.production`；默认门禁离线精简。
- 不读取、输出或提交密钥、`.env.production`、模型原文、真实原始数据或私有路径。

## 读取预算

- 恢复只加载本卡；源码先用 `rg -n -m 5` 定位，首轮最多读 2 个源码和 1 个测试文件。
- 仅有具体缺口时运行 `scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8` 或 `-Diagnostics`。
- 本卡超过 2KB 时立即压缩。
