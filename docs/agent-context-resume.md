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
- M242 已完成：将 GeoJSON 空间摘要默认上限从 100 KB 提升到 50 MiB，支持 `SPATIAL_AGENT_GEOJSON_MAX_BYTES` 配置并限制在 100 MiB 硬上限内；运行、重试、HTTP 和会话入口的默认要素数统一为 10,000。新增预算配置回归，Docker 定向 GeoJSON/结果契约 24/24 通过，compileall 通过。
- M243 已完成：新增领域中立、版本化 `data_profile` 输出契约，支持 `unknown`、`text`、`vector`、`raster`、`metrics`、`timeseries`、`document_evidence` 和 `composite`；Result Registry 声明数据形态，公共 Result Envelope 统一输出和校验，GIS 与 Text Domain 已接入。重建 Docker 后 M243 + M46 定向契约 18/18 通过，compileall 通过；M122 中两个旧 HTML 实现断言仍是后续前端契约清理项，不影响本阶段生产代码。
- M245 已完成：将 `data_profile` 传播到 async result evidence 和 Console nested-schema，旧异步/前端载荷安全回退为 `unknown`；artifact 恢复继续使用同一嵌套 Result。重建 Docker 后 M245 + M243 + M46 Python 回归 20/20、Node nested-schema smoke 和 compileall 通过。
- M247 已完成：新增领域中立的 `spatial_operation` 工具 seam，支持 `clip`/`intersect`；输入可为配置矢量数据集或前一步 `result_ref`，Hybrid 后端支持行政区 GeoJSON 与 GeoPackage 矢量跨来源处理，统一完成 CRS 对齐、无效/空几何过滤、要素预算、缓存与 GeoJSON 导出；结果声明 `vector` 数据形态并提供结构化 view。新增规则编排与 M247 精简回归，Docker compileall、M247/M3 定向测试、quick 和 stage 全部通过；M50 中两个旧用户回答文案断言仍需后续清理，不影响本阶段。
- M248 已完成：沿用同一 `spatial_operation` seam 增加 `buffer` 与 `distance`；buffer 在米制 CRS 中生成并按 mask 限制范围，distance 为输入要素附加最近距离并支持阈值筛选，均保留原始 CRS、来源、预算、缓存、GeoJSON 导出和 `vector` 数据形态。新增 `vector_measurement` workflow/capability，删除 Rule Planner 对 KNN/最近问题的旧硬拒绝；Docker compileall、5 个 M248 定向用例、quick 和 stage 通过。
- M249 已完成：对“裁剪洪山区道路”做开放式 Planner context 验收，确认选中的 capability、workflow、`spatial_operation` schema 和 `spatial_operation_result` 会一起进入 LLM Planner；脱敏 fake LLM 仍通过标准 `LLMPlanner → TaskPlan` 解析，不增加 GIS 专用 prompt 分支。Docker compileall、M249+M229 context 回归 3/3、quick 和 stage 通过。
- M250 已完成：真实本地 GIS 的 `spatial_operation(distance)` 改为投影后 `sjoin_nearest`，避免对大范围 mask 构造全量 union；真实数据隔离验收完成，68903 条道路与 20923 个水体要素在 100 米阈值下返回 10000 条、保留距离统计和截断证据，未再超时。洪山区裁剪因真实行政区查询未匹配到几何而进入既有有限 replan；Runtime 保留降级完成语义，但公共回答新增明确的“原计划部分步骤未完成、当前为降级结论、可修复后重试”提示。Docker M80/M247/M249/M229 定向回归 23/23、quick、stage、compileall 通过。真实模型显式验收本轮因 provider timeout 在规划阶段失败（0 个工具步骤），已与 GIS 执行问题分开记录。
- M251 已完成（第一纵向切片）：新增显式注册的 `indicators` Domain Pack，用两个 ToolRegistry 工具支持指标目录发现和 latest/trend/compare 查询；新增领域中立 `array` workflow constraint，区域列表通过标准模板编译、计划校验和 Runtime 澄清。结果分别声明 `metrics`、`timeseries`、`composite`，View 复用 generic/table/chart renderer，HTTP `/domains/indicators/runs` 返回结构化 workspace。默认指标数据明确标注为 demo fixture，可由 `SPATIAL_AGENT_INDICATOR_DATA` 替换；M251 定向回归 3/3，跨 Domain/空间回归 35/35，quick、compileall 和 HTTP contract 通过。
- M252-A 已完成：M251 已单独提交并推送为 `22cdeee`；新增架构地图、兼容矩阵和 `scripts/architecture_check.py` 静态边界守卫。Docker 指标定向 3/3、compileall、quick、stage 通过；当前未移动业务实现。
- M252-A CI 回归已修复：GIS `spatial_relation` View 删除未定义且未使用的 `operation` 引用，新增最小 View contract；Docker service smoke、CI profile 和 compileall 通过。
- M252-B1 已完成：新增 `domains/gis/adapters/spatial.py` canonical seam，GIS Domain 不再直接导入公共 `agent` 的 DatasetCatalog/spatial_backend；旧实现暂留兼容。
- M252-B2 已完成：GIS 的 spatial/raster/alignment/quality/catalog/manifest/probe/geometry-export 真实实现已迁入 `domains/gis/adapters`，`agent/` 仅保留单向 facade；新增兼容模块登记和迁移回归。干净 Docker 重建后 M252 定向 9/9、architecture strict、quick、stage、compileall 全部通过。
- M253-A 已完成：新增 `agent/runtime_core/projection.py`，Runtime 的计划 DAG、workflow context 压缩、模板匹配、结果引用解析和生命周期投影改为 canonical pure seam；`agent.runtime` 保留薄兼容 wrapper。干净 Docker 重建后 M253/M252/M247 定向 12/12、architecture strict、compileall、quick、stage 全部通过。
- M253-B 已完成：新增 `agent/runtime_core/planning.py`，Runtime 的 Planner 调用、通用计划校验和能力选择澄清改为 canonical seam；Domain validator/repair 仍由 Runtime 编排。干净 Docker 重建后 M253/M252/M247 定向 14/14、architecture strict、compileall、quick、stage 全部通过。
- M253-C 已完成：新增 `agent/runtime_core/execution.py` 与 `StepExecutionHooks`，ToolRegistry dispatch、工具超时、有限重试、步骤状态、终态事件和 pending 阻断改为 canonical execution seam；Runtime 仅注入 Domain preflight、控制检查和观测回调。干净 Docker 重建后 M253/M252/M247 定向 16/16、architecture strict、compileall、quick、stage 全部通过。
- M253-D 已完成：新增 `agent/runtime_core/control.py` 的 `RunControl`，取消集合、持久取消状态和 deadline 检查统一收敛；Runtime 不再直接持有控制锁/取消集合。干净 Docker 重建后 M253/M252/M247 定向 17/17、architecture strict、compileall、quick、stage 全部通过。
- M254-A 已完成：新增 `agent/application/run.py` 的 `RunApplication`，同步 run 的结果/provenance/failure/result contract、artifact/GeoJSON、SQLite、memory 和 async quiescence 收口已移出 Service；`AgentService._run_governed` 为兼容 wrapper。Docker M78/M253/M252 定向 15/15、architecture strict、compileall、quick、stage 全部通过。
- M254-B 已完成：新增 `agent/application/sessions.py` 的 `SessionApplication`，SessionState/SQLite/Runtime clarification 清理收敛到 `ServiceState`，AgentService session 入口改为 wrapper。显式清除生产 DB 环境后 M254/M78/M48/M68 回归 12/12，architecture strict、compileall、quick、stage 全部通过。
- M254-C 已完成：新增 `agent/application/actions.py` 的 `ActionApplication` 与 `agent/application/decisions.py` 的 `DecisionApplication`；Domain action 的 dispatch、幂等 artifact 回放、执行记录、观测，以及 Decision lookup/approve/reject/原计划恢复均从 Service 下沉。通用 action receipt 的 CAS、transition lineage、evidence revalidation 和 artifact receipt 也收敛到 ActionApplication；修复交互 dispatch 缺失 canonical interaction projection，并清理旧前端静态 URL 断言与矛盾的 action 输入错误码测试。Docker 68 项 action/decision/interaction 定向回归、architecture strict、compileall、quick、stage 全部通过，Service 规模降至约 2,560 行。
- M254-D 已完成：新增 `agent/application/interactions.py` 的 `InteractionApplication`，统一 interaction command 规范化、权威状态重读、allowlist dispatch、workflow continuation、preview/run continuation 和 receipt 完成；Service 只保留两个 Domain capability/facts 解析适配端口。Docker 66 项 action/decision/interaction 回归、M254/M48/M68 8 项、architecture strict、compileall、quick、stage 全部通过，Service 规模降至约 2,282 行。
- M255 已完成：新增 `agent/application/async_runs.py` 的 `AsyncApplication`，统一异步提交幂等、SQLite claim、memory job、worker 异常落盘、重启接管、artifact-only 观测恢复、取消标记、终态观测和 metrics；Service 仅保留兼容入口、线程池资源生命周期和 RunApplication 回调端口。修复 worker 动态替换接线，以及 async artifact evidence 规范化遗漏 `model_evidence`、`answer_generation` 和 runtime fingerprint 的跨入口不一致。Docker 异步/SQLite/artifact/restart 回归 28 项通过、1 项按配置跳过；architecture strict、compileall、quick、stage、smoke 全部通过，Service 约 1,773 行。
- M256 已完成：新增 `agent/application/http.py` 的统一 `HTTPApplication` 读写 seam；FastAPI 与标准库入口的 run/async/preview/retry/cancel/interaction/decision/session/action/workflow/domain routing，以及 run/evidence/interaction/async observability/session/metrics/memory/action history/capability/artifact manifest/evidence 读操作均经同一 application dispatcher。transport 只保留 URL 解析、状态码和 artifact 路径安全；更新 M78 静态契约为新 seam。Docker M256/HTTP/Domain/artifact 定向 16/16、Runtime/Application/async/restart/artifact 回归 31/31、quick/stage/smoke、compileall、architecture strict 和 Console map/session/selection smoke 全部通过。
- M242 的本地提交和 GitHub 推送状态以 `git log -1` 与远端分支为准；此前 GitHub push 曾因宿主网络超时，现已恢复并成功推送到 `origin/main`，不要重复实现已完成阶段代码。
- 最新生产镜像 healthy；聚焦回归 23/23、quick/stage/smoke、compileall 和 M230 显式浏览器验收通过；M231 的 Browser 控制进程初始化异常已单独记录。

## 下一步

当前 Goal 的 Runtime 验收标准、M233 控制台/布局阶段、M240 回答生成边界、M242 GeoJSON 导出预算、M243/M245 输出数据形态跨入口传播、M247/M248 通用空间算子、M249 开放式 Planner context、M250 真实本地 GIS 空间算子和 M251 指标 Domain 第一纵向切片均已闭环。M252-A 基线冻结、M252-B1/B2 GIS 物理边界、M253-A/B/C/D Runtime seams、M254-A/B/C/D Run/Session/Action/Decision/Interaction seams、M255 Async Worker/Recovery seam 和 M256 HTTP read/write dispatcher seam 已完成；下一阶段从全局架构收敛 Contract/Evidence helper，随后进行 Vite 前端源码与构建产物物理拆分，再清理已确认无引用的兼容入口。真实指标数据接入顺延到公共边界收敛后。继续保持少量深工具、公共 Runtime 不携带领域策略，不引入 RAG，也不为固定问句增加分支。

## 不变量

- Runtime 领域中立；能力通过 facts/catalog/schema/workflow/result/view 扩展，不写区域或固定问句分支。
- Python 测试和 compileall 只在 Docker；Docker compose 必须显式使用 `--env-file .env.production`；默认门禁离线精简。
- 不读取、输出或提交密钥、`.env.production`、模型原文、真实原始数据或私有路径。

## 读取预算

- 恢复只加载本卡；源码先用 `rg -n -m 5` 定位，首轮最多读 2 个源码和 1 个测试文件。
- 仅有具体缺口时运行 `scripts/resume_context.ps1 -Topic "关键词" -MaxMatches 4 -ContextLines 8` 或 `-Diagnostics`。
- 本卡超过 2KB 时立即压缩。
