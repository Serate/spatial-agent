# Agent 开发问题记录（当前索引）

本文件用于记录近期仍有参考价值的工程问题，使用中文维护。每条问题至少包含：现象、根因、诊断、修复和预防。历史条目已归档到 `docs/archive/context-history/agent-development-issues-history.md`，恢复上下文时不得全文读取。

## 服务端答案 delta 已存在但前端仍一次性显示

- **现象**：真实模型运行已经产生多个 answer_delta，但用户在页面上看到答案像一次性出现，无法获得 Codex/Claude Code 类似的逐字反馈。
- **根因**：console_app.js 收到每个 delta 后直接同步设置 answer.textContent；provider chunk 大小和 SSE 到达速度会进一步放大浏览器尚未绘制就连续处理完事件的观感。服务端增量事件本身并不等于前端逐字渲染。
- **诊断**：先用单个完整 chunk 驱动实际 handleLiveEvent，在终态前断言 DOM 不能等于完整 chunk；再读取同一 run 的 SSE 帧，只统计事件数和字符数，不输出答案、Prompt 或模型原文。若真实 run 有多个 delta 但前一断言失败，问题位于前端消费节奏，不要重复调用模型或修改计划/工具参数流。
- **修复**：新增领域无关的 ConsoleAnswerStream，将 delta 放入有界队列，每个 requestAnimationFrame（无支持时使用定时器）最多消费一个 Unicode code point；终态 finish() 可等待队列排空，并对与最终结构化摘要不一致的前缀执行安全校正。运行取消或切换时重置队列；新增脚本加入静态资源白名单。
- **预防**：实时体验验收必须同时覆盖“服务端产生多个 delta”和“终态前 DOM 多次变化”两条边界；答案可以逐字显示，但结构化计划、工具参数、隐藏思维链、Prompt 和敏感信息不得流入展示层。大 chunk 不应在 provider 层强行拆成伪 token，前端节奏化是独立的呈现策略。

## Provider 重试期间前端长期停留在“正在生成任务计划”

- **现象**：真实模型请求失败前，页面长时间显示“正在生成任务计划”，用户容易误以为页面卡死。
- **根因**：provider 默认每次请求有 60 秒期限并允许 2 次重试；规划阶段只有开始和结束事件，阻塞 HTTP 调用期间没有新的阶段事件，最终一次失败 Run 的等待时间可接近 3 分钟。
- **诊断**：读取同一 Run 的状态和事件，不重复提交模型请求；若状态由 PLANNING 变为 FAILED，事件包含终态，且安全 evidence 为 planning/provider_timeout、attempts=3、retries=2，则问题是 provider 等待体验而不是 SSE 丢事件或前端旧资源。
- **修复**：Console 在规划阶段等待超过 12 秒后，在实时摘要和副标题明确显示“模型响应较慢，仍在等待返回”及累计等待时间；真实事件或失败终态到达后覆盖该提示，不伪造进度、重试次数或工具状态。
- **预防**：实时 UI 必须区分“等待 provider”和“运行时无事件”；默认保留真实 heartbeat、耗时和 transport 信息。provider 的 timeout/retry 策略应继续由配置和 evidence 控制，不能用前端动画掩盖失败。

## Async Application 迁移后 worker 仍需保留动态执行端口

- **现象**：异步应用已从 `AgentService` 下沉后，测试通过 `patch.object(service, "run", ...)` 注入 worker 异常时，任务仍然执行成功；另外旧测试对 `agent.service._process_is_alive` 的 patch 可能失效。
- **根因**：迁移时把绑定方法对象直接传给 Application，worker 保存的是构造时的旧引用；同时进程存活判断没有通过可注入端口连接到兼容 facade。
- **诊断**：用“worker 抛异常”和“重启接管”两条路径分别检查注入函数是否在 worker 执行时解析；不要只看 Application 是否成功构造，也不要把测试 patch 误判为业务执行问题。
- **修复**：`AsyncApplication` 通过 `run_provider` 和 `process_is_alive` 注入端口，Service 传入运行时解析的 lambda；线程池仍由 Service 创建和关闭，Application 只决定调度与生命周期语义。
- **预防**：迁移异步 worker 时，凡是允许自定义 Runtime、测试替换或兼容扩展的入口都不能冻结为构造时绑定的方法；为提交、worker 异常、claim/recovery 和资源关闭各保留一条最小契约。

## Async artifact 规范化遗漏模型与回答证据导致恢复结果不一致

- **现象**：实时 `get_async_observability()` 返回了 `model_evidence` 和 `answer_generation`，但写入 artifact 后再恢复时字段消失，或模型运行时 fingerprint 不一致；同一个 run 的 polling 与 artifact evidence 比较失败。
- **根因**：`build_async_result_evidence()` 已经输出这两段有界证据，但 `normalize_async_result_evidence()` 作为 artifact 边界投影没有同步保留；artifact 又不保存完整 runtime context，导致仅依赖 context 重新计算 fingerprint 会丢失身份。
- **诊断**：对同一个带 artifact 的 async run，依次比较实时 observation、artifact 的 `async_result_evidence` 和空 SQLite 重启后的 observation；按字段 diff，不要只比较顶层 status。确认请求、模型原文、密钥和主机路径没有进入证据。
- **修复**：规范化器复用 `project_model_evidence`/`project_answer_generation_evidence`，并只在固定 `sha256:<64位十六进制>` 形状通过校验时保留已有 runtime fingerprint；未通过校验的值丢弃，不猜测上下文。
- **预防**：新增 Result/Evidence 字段时必须同时审计 builder、async normalize、artifact write/read、SQLite restart 和前端 nested schema；验收至少包含 live polling 与 artifact-only recovery 的等价性，而不是只跑同步结果。

## 通用空间算子未进入统一 ToolRegistry seam

- **现象**：已有 `spatial_join` 能返回空间关系计数，建设筛选内部也有道路/水体几何约束，但开放式问题无法复用“裁剪”或“相交”这类几何操作；如果继续复制领域专用工具，Planner 和前端会被固定数据集绑定。
- **根因**：后端缓存、CRS 处理和几何导出能力分散在多个 Adapter 中，没有一个可组合的输入/输出契约；内存后端又没有真实矢量几何，不能伪造成功结果。
- **诊断**：从 ToolRegistry schema、SpatialToolAdapter、Hybrid/GeoPackage/GeoJSON 结果引用和 `data_profile` 一起检查；用配置数据集 ID 与已完成 `result_ref` 分别验证，确认 CRS、空/无效几何和 `max_features` 是否有界；不要只调用内部建设筛选函数。
- **修复**：增加领域中立的 `spatial_operation`，第一阶段只允许 `clip`/`intersect`；真实文件 Adapter 共享同一深模块实现 CRS 对齐、几何清理、结果缓存和导出，Hybrid 支持跨来源；内存后端返回 `vector_geometry_unavailable` 的可恢复错误；GIS Catalog、workflow、Result Registry、view 和规则编排均只声明这一小接口。
- **预防**：新增空间算子优先扩展操作枚举和稳定结果契约，不为区域或固定问句新增分支；输入只接受数据集 ID 或已注册结果引用，不接受原始 GeoJSON、文件路径或未注册数据；每个操作必须保留来源、CRS、预算、截断状态和 `vector` 数据形态，并通过 Registry、Docker 精简测试和显式真实 GIS 验收。

## 历史回答文案断言没有随公共回答契约迁移

- **现象**：M247 定向代码通过，但运行旧 `tests.test_m50_vector_workflow` 时，两个测试仍要求回答包含 `OpenStreetMap` 或“数据预检”；当前回答已经改为面向用户的短中文总结，因此出现失败。
- **根因**：测试锁定了旧 Composer 的附加文案，而不是验证结构化结果、工具身份和用户语义；这与 M240/M241 的回答边界升级不一致。
- **诊断**：比较失败断言和当前 `AnswerComposer` 输出，确认运行状态、工具结果和 Result Contract 均正常；不要为了兼容旧句式把内部来源或执行术语重新塞入用户回答。
- **修复**：本阶段不回退生产回答，也不把该旧测试加入 M247 门禁；后续清理 M50 时，应改断言为结构化来源/结果字段和稳定用户语义，或删除重复的旧文案测试。
- **预防**：回答测试只锁定公共语义和结构化证据，不锁定 Composer 的历史句式、内部引用或可选来源说明；每次 Answer Generation/Composer 变更都同步审计测试和 smoke。

## 已注册的最近距离能力仍被旧 Planner 入口硬拒绝

- **现象**：M248 已注册 `distance` 空间算子，但 Rule Planner 在进入能力路由前看到“最近”或“KNN”就直接澄清，导致新工具、Catalog 和 workflow 永远无法执行。
- **根因**：早期 M1 只支持固定范围关系查询，入口保护条件没有随着通用空间算子扩展而迁移；拒绝逻辑位于 Domain Planner 外层，单测后端工具无法发现该问题。
- **诊断**：从自然语言入口运行“最近距离/缓冲”请求，比较 Planner 是否产生 `spatial_operation`，再分别检查工具 schema、路由、workflow 和后端；不要只直接调用 Adapter。
- **修复**：删除过时的 KNN/最近硬拒绝，让请求进入 `vector_measurement` 路由；缺少输入、掩膜或缓冲距离时由通用编排返回结构化澄清，已注册能力可以继续执行。
- **预防**：新增能力时搜索所有入口级拒绝、早退和 capability allowlist；测试至少覆盖自然语言路由、显式 workflow 和 ToolRegistry dispatch，不能只覆盖底层算法。

## 单一 workflow 的可选参数无法表达操作特定约束

- **现象**：`clip/intersect` 不需要距离参数，而 `buffer/distance` 需要 `distance_m`；如果把它们放在一个 workflow blueprint 中，缺少可选约束时会生成 `None`，或为了绕过校验而静默使用不合理默认值。
- **根因**：workflow schema 采用静态 placeholder，暂不支持按 `operation` 条件渲染参数；强行复用一个 template 会让输入契约变浅或把操作语义隐藏在运行时。
- **诊断**：分别编译 `vector_operation` 和 `vector_measurement`，检查 required constraints、工具 args 和 Registry schema；不要只验证直接调用时的默认参数。
- **修复**：保持一个底层 `spatial_operation` 工具 seam，但拆成两个清晰的 Domain workflow：几何裁剪/相交与距离/缓冲各自声明操作枚举和必需约束；实际算法仍共享同一后端实现。
- **预防**：工具数量可以少，但操作特定约束必须在 schema/workflow 中显式表达；只有真正共享输入、输出和失败语义的能力才共用工具，不能为减少模板数量牺牲可校验性。

## 开放式 Planner 验收只看工具列表会漏掉能力选择上下文

- **现象**：仅验证 `LLMPlanner` 的注册工具列表，无法证明模型看到了当前选中的 capability、workflow 和结果类型；新通用工具可能在列表中存在，却没有足够元数据指导模型组合。
- **根因**：LLM Planner 的上下文由 Runtime 先投影，工具 schema、能力目录和 workflow selection 是不同 section；只测试模型返回一个合法 TaskPlan，不能证明这些 section 已进入 prompt。
- **诊断**：用一个不依赖网络的 fake LLM 构造真实 Runtime context packet，检查 selected capability/workflow ID，再检查传给 LLM 的有界消息是否包含工具名和 result type；不要读取或保存模型原文、密钥或真实请求数据。
- **修复**：新增 M249 context 验收，验证选中的 `vector_operation`、`spatial_operation` schema 和 `spatial_operation_result` 同时进入标准 LLM Planner；现有运行时已具备 selected-capability 过滤，不盲目扩大所有目录的 token 投影。
- **预防**：每个新能力都要增加一条“选中能力 → Planner context → TaskPlan”契约测试；真实模型调用只作为显式 live 验收，默认 CI 使用脱敏 fake/replay，防止 token 消耗和外部网络成为日常门禁。

## 新增结果字段只进入同步契约，异步和前端兼容层没有同步接入

- **现象**：同步 HTTP 或 artifact 中已经有新的结构化结果字段，但异步轮询 evidence 或浏览器兼容层恢复旧形状，导致不同入口看不到同一结果分类。
- **根因**：async evidence 是独立的有界投影，Console 还有独立的 nested-schema 校验；只修改公共 Result Envelope 不会自动覆盖这些传输和恢复 seam。
- **诊断**：对同一结果分别比较同步 Result、async polling evidence、artifact read/recovery 和 Console Node smoke，重点检查 schema version、字段是否被有界投影保留；不能只验证一次同步调用。
- **修复**：新增 `data_profile` 后，同时在 async build/normalize、artifact 嵌套 Result 和 Console nested-schema 中增加版本校验与 legacy `unknown` 回退；用 artifact、async 和 Node smoke 做跨入口最小回归。
- **预防**：任何 Result Contract 新字段都必须列出同步、异步、artifact、SQLite recovery、HTTP 和前端兼容层的传播清单；投影字段缺失时要有明确的 legacy 状态，不得静默猜测业务类型。

## 结果业务语义与数据形态没有统一分类

- **现象**：结果类型已经能够区分“综合空间分析”或“栅格统计”，但公共 Result Contract 没有明确声明结果包含矢量、栅格、指标、时序或文档证据；前端和新领域只能继续根据工具名或领域结果类型猜测展示方式。
- **根因**：早期的 `result_type` 同时承担业务语义、数据形态和展示路由，Domain Registry 只有标题、面板和 renderer 信息，没有领域中立的数据形态契约。
- **诊断**：检查 Result Envelope 是否有版本化数据形态字段，并比较 GIS、Text 等不同 Domain 是否能通过同一 Registry 接口声明；不要只检查某个 GIS View 是否能绘制。
- **修复**：新增版本化 `data_profile`，支持 `unknown`、`text`、`vector`、`raster`、`metrics`、`timeseries`、`document_evidence` 和 `composite`；由 `ResultTypeSpec` 声明，由公共 Result Contract 统一输出和校验，旧 artifact 缺失该字段时迁移为 `unknown`。
- **预防**：`result_type` 只表达业务语义，`data_profile` 表达数据形态，View 只表达展示方式；新增 Domain 先声明结果形态，再实现专用 View。不要把行业名称或具体工具名写入公共 Renderer 分支。

## GeoJSON 空间摘要上限过小导致地图只能看到部分结果

- **现象**：空间分析生成的 GeoJSON 摘要默认只有 100 KB，且默认最多导出 100 个要素；较大的道路、水体或候选区域结果会被截断，前端只能绘制部分空间要素。
- **根因**：早期为了限制 artifact 和浏览器负载设置了过于保守的固定上限，字节上限与要素数量上限又分散在多个 Service、HTTP 和会话入口，导致只调大其中一个仍可能看不到完整结果。
- **诊断**：检查 GeoJSON artifact 的 `properties.geometry_truncated`、实际文件大小和 `features` 数量；同时搜索 `geojson_max_features` 的所有默认值，不能只检查导出器的 `max_bytes`。
- **修复**：默认 GeoJSON 摘要上限提高到 50 MiB，支持 `SPATIAL_AGENT_GEOJSON_MAX_BYTES` 配置，并设置 100 MiB 硬上限；所有运行、重试、HTTP 和会话入口的默认要素数统一提高到 10,000。保留截断证据，前端继续明确提示“结果可能不完整”。
- **预防**：大文件上限只适合本地 GIS 或显式验收，不应无限增大；真实生产数据量继续增长时，应按 bbox/zoom 分块或采用矢量瓦片。新增入口必须复用统一默认常量，并用一个精简测试同时覆盖默认预算、环境配置和硬上限。

## 用户回答契约升级后 CI 仍断言内部引用

- **现象**：GitHub CI 的稳定契约和 service smoke 同时失败，邮件提示 `Some jobs were not successful`；运行状态和工具步骤实际均已完成。
- **根因**：回答从模板内部结果引用迁移为用户可读中文后，`tests/test_dev_gate.py` 与 `scripts/smoke_check.py` 仍要求答案包含 `memory://range/admin_areas`，测试契约没有随公共回答边界更新。
- **诊断**：先运行 `python scripts/test_profile.py --profile ci`，查看 profile 返回的两个子检查；区分“业务运行失败”和“断言只接受旧内部表示”。
- **修复**：断言行政区边界等用户语义，并明确禁止 `memory://` 出现在回答中；保留工具名、结果类型和结构化证据在内部契约中验证。
- **预防**：回答文案变更必须同步搜索测试、smoke、评测和前端断言中的内部引用；CI 只验证公共语义和结构化结果，不锁定 Composer 的旧句式或 artifact ref。

## 领域 Composer 直接拼接最终回答，导致真实模型模式仍像程序日志

- **现象**：工具执行成功后，回答出现“完成几个工具步骤”、内部字段或固定句式；用户难以理解综合结果，且新增领域或开放式问题需要不断增加模板分支。
- **根因**：早期为了离线稳定、事实可控和模型不可用时可降级，真实模型只参与 Planner，最终回答一直由 Domain Composer 手写生成；系统没有独立的回答生成边界。
- **诊断**：检查运行时成功路径是否只调用 `answer_composer.compose`，以及 `planner_metrics` 是否被误当成回答模型证据；中转的 `json_object` 模式可能忽略 `additionalProperties: false`，需检查返回字段集合而不是只检查 JSON 是否可解析；不要把前端文案问题误判成工具执行问题。
- **修复**：增加 `agent.answer_generation`：Runtime 先保留 Domain Composer 作为可信回退，再将请求、目标和工具结果的有界脱敏事实投影给结构化回答模型；回答通过字段集合、schema、长度和内部引用校验后才替换模板，并在失败时回退。提示词明确要求只返回 `answer` 字段，以兼容中转服务。
- **预防**：模型只负责自然语言表达，不负责事实、证据、权限和工具结果；默认/离线模式不调用模型，真实模型模式单独记录 `answer_generation` 有界证据；同步、异步、artifact 和 SQLite 恢复都只读取最终回答与脱敏证据，不保存 prompt、原始响应、密钥或私有路径。

## 多领域目录存在但运行、恢复仍被单例服务固定

- **现象**：`/domains` 能列出 GIS/Text，但同一 HTTP 进程只能执行启动时选中的领域；切换领域后，run、artifact、异步恢复和会话可能被当前服务领域过滤，或共用幂等键和澄清状态。
- **根因**：`DomainRegistry` 只负责目录和构造，两个 HTTP 入口仍各自持有一个模块级 `AgentService`；SQLite 会话没有领域绑定，异步与 interaction 的幂等键又是全局唯一。
- **诊断**：分别检查 URL 领域、Service 配置领域、持久化 payload/runtime context/result/artifact 的 `domain_id`，再用同一 SQLite 同时提交 GIS/Text；不能用两个独立进程通过来证明单部署多领域。
- **修复**：增加版本化 `DomainSelection` 和 `DomainRuntimeHost`，每个领域持有独立 Service 并在启动时全部预热恢复；新增 `/domains/{domain_id}/...` 路由，URL 为权威来源；会话持久绑定一个领域，异步和 interaction 幂等键在存储层按领域命名空间化，artifact 写入拒绝跨领域覆盖。
- **预防**：任何新入口都必须携带或恢复记录自身领域；轮询、取消、重试和 artifact 链接不得读取当前下拉框或模块单例的隐式领域；跨领域 Host、HTTP、SQLite 和 Console 使用一条精简专项验收。

## 多领域浏览器 smoke 在 CDP 缺失和旧插件缓存下长时间等待

- **现象**：前端实现已经写入，但 subagent 长时间不返回；手动运行后，动态领域 smoke 可通过，清空 smoke 却仍看不到新增的 SVG fallback 点击上下文。
- **根因**：验收任务默认等待 `127.0.0.1:9222`，没有先确认隔离 Chrome CDP；运行中的 Chrome 又缓存了旧 GIS plugin。旧清空 smoke 只等待全局函数存在，并且只接受 Leaflet path，不接受无外网时的 SVG fallback。
- **诊断**：先执行 `node --check` 和静态 seam 检查，再确认 `/json/version`、页面 profile、资源版本和 renderer report；区分“renderer 已绘制”与“旧资源未加载/点击选择未绑定”。
- **修复**：停止无界等待，显式启动隐藏的隔离 Headless Chrome；重建干净 profile 后串行运行 smoke；清空 smoke 等待 Domain bootstrap ready，并同时支持 Leaflet 与 SVG path；GIS plugin 为 SVG fallback 增加点击和键盘选择。
- **预防**：CDP smoke 启动前必须有界探测，单页串行执行并在阶段结束关闭本次 PID；资源实现改变后使用干净 profile 或 cachebuster；fallback 也是正式适配器路径，必须验证绘制、交互、context 和 reset。

## 静态测试锁定局部变量名造成误报

- **现象**：CDP 启动器已正确使用独立临时 profile，但 compact 测试因变量由 `$profile` 改名为 `$cdpProfile` 而失败。
- **根因**：测试断言实现中的局部变量拼写，没有验证“`--user-data-dir` 引用变量且目录来自系统临时目录”这一真实行为契约。
- **诊断**：先检查失败标记是否影响外部行为；若只是等价重命名，不要为了通过测试回退生产代码。
- **修复**：用有界正则验证 `--user-data-dir=$变量`，并独立验证 `GetTempPath()`，保留“不停止现有 Chrome”等安全断言。
- **预防**：静态测试只锁定公开边界、安全不变量和必要标记，不锁定局部变量名、函数内排版或无语义字符串。

## 会话 smoke 把合法公共证据误判为串话

- **现象**：恢复 direct-answer 会话后统一结果容器显示该会话自己的执行证据，旧 smoke 却因容器可见而报告另一会话结果泄漏。
- **根因**：测试用 DOM 可见性代理结果身份；统一 renderer 迁移后，不同结果类型会共享同一容器，可见性不再能证明来源。
- **诊断**：检查恢复后的会话 ID、消息历史和结构化结果类型，再搜索另一会话独有的 result/tool identity。
- **修复**：断言当前容器包含 `direct_answer`，同时排除另一会话的 `raster_metadata` 与 `get_raster_metadata` 标识。
- **预防**：跨会话隔离测试比较结构化身份和 lineage，不以面板选择器、可见性或自然语言中的偶然词汇判断泄漏。

## 恢复上下文载入过量

- **现象**：新对话按旧约定依次读取恢复档案、任务档案和完整问题日志，三份文件累计数十万字符，当前阶段和阻塞项被历史内容淹没。
- **根因**：历史文档长期追加，虽然文首写了“不要全文读取”，但文件路径本身仍会诱发全文加载；启动入口和历史档案没有物理分离。
- **诊断**：先检查文件大小和恢复脚本的默认路径，再确认当前短快照是否能独立说明目标、阶段、证据和下一步。
- **修复**：将入口与状态合并到 `docs/agent-context-resume.md`，删除重复的 current 快照；`scripts/resume_context.ps1` 默认只输出这一份恢复卡，Git 诊断改为显式 `-Diagnostics`，历史仅通过 `-Topic` 有界检索。
- **预防**：恢复默认文件数固定为 1、历史文件数为 0；不要为了恢复再加载 skill；源码最多按需定位 2 个文件、测试最多 1 个文件；恢复卡超过约 2KB 时先压缩。`task-resume`、问题日志和 milestones 只按需读取。

## 复合能力的 HTTP 首次结果缺少组件证据

- **现象**：复杂 GIS 请求的 HTTP `POST /runs` 结果只有核心 7 个 Evidence Registry entry，detail、artifact 或后续恢复路径预期的 `workflow_component_evidence` 不一致。
- **根因**：自动发现只返回复合 capability，没有返回稳定的 workflow component identity；公共 Registry 正确地不猜测组件，因此首次结果无法建立组件证据索引。
- **诊断**：对 HTTP、detail、sync artifact、async、recovered、async artifact 分别只投影 `evidence_registry.entries[].id`，并检查 `plan_evidence.workflow_selection.workflow_components` 是否为空。
- **修复**：由 GIS Domain 根据结构化任务事实声明复合组件；公共 `workflow_selection`、Registry 和跨入口 projection 继续保持 Domain-neutral。
- **预防**：任何自动或显式组合能力都必须在 selection 阶段提供稳定 component identity，并在同步、HTTP、Artifact、Async、SQLite recovery 中比较同一组 evidence entry；不得从 result type 或固定问句临时推断。

## 扩展通用事实后 workflow catalog 被上下文预算裁剪

- **现象**：为 `RequestFacts` 增加通用实体字段后，复杂请求的上下文优先丢弃 workflow catalog，`plan_evidence.matched_template_ids` 变为空，虽然 Runtime 仍能执行计划。
- **根因**：ContextBuilder 按固定顺序裁剪 section，workflow catalog 比大型 advisory capability catalog 更早被删除；新增合法事实扩大了输入但没有改变优先级。
- **诊断**：只检查 `context_evidence.section_names`、`section_chars`、`workflow_templates.omitted` 和 `plan_evidence.template_context_available`，不要读取完整模型上下文。
- **修复**：预算不足时先裁剪 capability catalog/discovery，再保留 workflow catalog、selection 和可执行工具信息；新增实体同时保留在结构化 facts 中。
- **预防**：上下文 section 必须有稳定优先级；新增公共事实后至少回归复杂计划的模板匹配、LLM context seam 和 bounded render，不能只验证最终工具步骤成功。

## Docker 测试容器读取旧源码

- **现象**：宿主工作区已经新增测试或修复代码，但 `docker exec` 中的 unittest 仍看不到新测试；容器状态正常却验证了旧版本。
- **根因**：生产 Compose 只挂载 `outputs` 和数据目录，源码通过 Dockerfile 的 `COPY . /app` 固化进镜像，没有工作区源码卷挂载。
- **诊断**：比较宿主与容器中的测试模块路径、测试方法列表和镜像构建时间；不要仅依据容器 `healthy` 判断代码版本同步。
- **修复**：源码变化后使用 `docker compose -f docker-compose.prod.yml build spatial-agent`，再使用 `docker compose -f docker-compose.prod.yml up -d spatial-agent` 重建容器，然后在容器内执行测试和 compileall。
- **预防**：默认 Docker 验收必须先确认镜像包含当前提交；开发阶段可使用专用源码挂载 Compose 配置，但生产 Compose 继续保持不可变镜像，不把宿主源码直接暴露给生产容器。

## 精简回归暴露候选路由与能力目录证据不稳定

- **现象**：泛化请求“洪山区有哪些地方适合建设”被选为专用 `buildability_screening`；HTTP 复杂请求的 `capability_catalog_available` 变为 `false`，结果中缺少 `capability_catalog_ids`。
- **根因**：专用 GIS 路由只依据 `buildability` 任务排序，没有区分明确的建设适宜性信号；上下文裁剪先丢弃了紧凑能力目录；证据投影没有为目录不可用场景提供稳定的空数组。
- **诊断**：只运行 M77 的路由用例和 M81 的 HTTP/Artifact 契约用例，检查 `selected_capability_id`、`context_evidence.section_chars`、`plan_evidence.capability_catalog_available` 和 `capability_catalog_ids`。
- **修复**：GIS Domain 增加独立 `buildability` lexical signal；ContextBuilder 优先裁剪 advisory discovery、保留能力目录和 workflow selection；Runtime 证据始终输出 `capability_catalog_ids` 与 schema count 的默认值。
- **预防**：新增专用路由必须同时验证泛化表达、明确表达和复杂组合表达；上下文裁剪按“可执行目录/工作流优先、advisory 信息可丢弃”排序；所有公共证据字段在不可用时也保持契约形状。

## 动态 View 迁移中的嵌套 rows 与浏览器 smoke 竞态

- **现象**：统一前端 renderer 接管 GIS view 后，健康检查仍显示指标，但 `admin_areas` 等 rows 变成“字段 -”；健康 smoke 偶尔读取上一页的“已完成”状态，未真正执行本轮请求。
- **根因**：旧 renderer 假设 rows 使用 `label/value`，而 Domain view 使用 `dataset/status/count/detail`；smoke 未等待 `sendChat`、新会话和页面 ready 状态。
- **诊断**：只检查 `views.panels.health.rows` 的实际字段，并观察 smoke 是否有工具名、动态 slot 状态和新运行 ID；不要用状态文字单独判断请求完成。
- **修复**：通用 renderer 对 rows 使用有界字段投影并保留嵌套对象；健康 smoke 等待页面 ready、新会话和 `sendChat`，同时断言工具名与关键数据集。
- **预防**：新增 Domain view 只依赖公共 `metrics/rows/table` 和有界对象投影；浏览器 smoke 必须等待明确请求完成，并同时校验结构化内容、面板状态和执行工具。

## 异步轮询缺少同步结果的模型证据

- **现象**：同步结果包含 `model_evidence`，但异步 `result_evidence` 只有 view、selection 和生命周期字段，live/replay 模式与上下文指纹无法在轮询入口确认。
- **根因**：同步结果契约内部实现了模型指标投影，异步模块没有复用同一投影接口，导致两个入口的证据形状漂移。
- **诊断**：对同一完成 run 比较同步 envelope、artifact 和 `/runs/{id}/async` 的 `model_evidence`；只检查 schema、execution mode、fixture/provider、usage 限幅和 context fingerprint，不读取原始模型响应。
- **修复**：新增领域中立的 `agent.model_evidence.project_model_evidence` 深 Module；同步、异步和前端异步摘要共享该接口，统一 allowlist、限幅和上下文指纹。
- **预防**：新增公共 evidence 字段必须同时验证 sync、async、artifact、SQLite recovery 和前端摘要；任何 provider raw response、prompt、密钥和路径都不得跨该 seam。

## 模型证据重复投影改变 available 状态

- **现象**：同一规则规划运行在完整 Result/Artifact 中为 `model_evidence.available=false`，经过异步 `result_evidence` 再投影后却变成 `true`，其余执行模式和上下文指纹一致。
- **根因**：公共投影函数用输入 Mapping 是否非空推断 available；规范化后的证据对象即使显式声明 `available=false`，Mapping 本身仍为非空。
- **诊断**：只比较同一 run 的 Result、异步 polling 和 Artifact 中 model evidence 的 schema、available、execution mode 与 context fingerprint，不读取模型响应。
- **修复**：`project_model_evidence` 优先继承显式布尔 `available`，仅在输入没有该字段时根据指标是否存在推断。
- **预防**：公共投影必须满足重复投影幂等；新增字段时至少验证 `project(project(x))` 的稳定语义，以及 sync/async/artifact 三个入口的一致性。

## 用 preview 哈希约束独立 live 规划导致误失败

- **现象**：真实模型 API 调用成功，Planner 指标状态为 success，但同步执行因 `plan_fingerprint_match=false` 返回失败；规则 Planner 不复现。
- **根因**：验收脚本先调用 preview，再让同步和异步分别重新调用真实模型并强制匹配 preview 哈希；真实模型可为同一请求生成语义等价但结构细节不同的合法计划。
- **诊断**：检查 expected/actual plan SHA-256、planner status、failure phase 和 error code；不要输出计划正文或模型原始响应。
- **修复**：同一 run 的 HTTP、polling、Artifact 必须严格比较 plan identity；两个独立 live run 只比较结果类型、模型身份、上下文、workspace 和 view，分别保留各自 plan identity 作为证据。
- **预防**：验收设计必须区分“同一运行的传输一致性”和“独立模型调用的语义稳定性”；preview 指纹只用于用户确认后执行等同一计划绑定场景。

## 插件化后历史测试仍要求固定 GIS 控件

- **现象**：Console 已改为从 Action Catalog 和 renderer registry 动态生成工作区，旧测试仍要求页面包含三个 GIS Action ID、固定对比按钮和领域控件标记，导致正确的隔离改造被报告为失败。
- **根因**：测试复制了旧页面实现，而不是验证“Shell 只消费 schema/renderer id、Domain 实现不泄漏”的接口；多个里程碑测试又重复锁定同一组 DOM。
- **诊断**：先搜索失败断言是否引用具体 Action ID、结果类型、局部函数或已删除 DOM；再检查 `/actions`、`view_specs` 和插件接口是否真实可执行。
- **修复**：静态契约改为断言 Registry、Action Host 和 Domain adapter 的小接口，并明确禁止 GIS Action/选择状态出现在 Shell；删除两条依赖固定 GIS 表单的重复浏览器 smoke。
- **预防**：Shell 测试只验证插件 seam、故障降级和领域隔离；Domain 专用字段只在对应 adapter 或显式 Domain smoke 中验证。删除的历史测试可从 Git 恢复，不再进入当前门禁。

## 地图 smoke 依赖可选数据和已删除的全局状态

- **现象**：地图交互 smoke 在当前 Docker 数据配置下因 `admin_areas dataset has no files` 失败；即使有数据，脚本仍读取已迁入 GIS adapter 的 `leafletMap` 和 `selectedSpatialContext` 全局变量。
- **根因**：一个前端交互测试同时承担真实数据可用性、地图绘制和选择状态验证；插件迁移后内部状态已不再属于 Console Shell。
- **诊断**：分别检查运行错误、renderer surface、DOM 矢量要素和 `rendererRegistry.context()`；不能把数据缺失与插件交互失败合并为一个结论。
- **修复**：地图/清空 smoke 使用内联脱敏 GeoJSON，只验证 map adapter 绘制、点击、上下文输出和 reset；真实 GIS 数据继续由显式 GIS/live 验收独立证明。
- **预防**：浏览器插件 smoke 默认使用最小确定性 fixture；真实数据、真实模型和浏览器交互保持分层，任何一层都不能替代另一层的证据。

## 自动选域澄清没有稳定会话身份导致 lineage 断裂

- **现象**：首次智能选择返回歧义后，用户选择 Domain 能生成 override decision，但继续 `/runs/auto` 时返回 decision not found。
- **根因**：前端为了避免提前创建某个 Domain 会话而完全省略 `session_id`；澄清 decision 以空会话保存，继续执行却落到默认会话，持久层正确地拒绝跨会话读取。
- **诊断**：比较首次 `/runs/auto`、decision select 和继续执行三次请求中的 `session_id`、`decision_id` 与 `parent_decision_id`，不要只看候选按钮是否出现。
- **修复**：前端生成 `conversation-auto-*` 中立 identity；它只绑定 routing lineage，不初始化 Domain。选中并执行后，同一 identity 才由 AgentService 绑定到实际 Domain，刷新从本地安全绑定恢复。
- **预防**：任何多步澄清都必须从第一步携带稳定 session identity；“未绑定领域”不等于“没有会话身份”。浏览器 smoke 必须验证 override 继续与刷新恢复。

## Selector 与 SQLite 恢复接缝信任了未验证输入

- **现象**：直接调用 Model Selector 时，调用方可在 snapshot 中夹带工具 schema；自定义第三 Domain 的合法 decision 无法持久化；篡改后的 SQLite JSON/列可能被直接返回。
- **根因**：allowlist 校验只覆盖模型输出，没有在模型调用前严格重建输入；SQLite adapter 恢复时使用全局 registry 且只做 `json.loads`，没有重验版本和列/JSON 一致性。
- **诊断**：向 snapshot 注入 `tools/input_schema` 并捕获模型输入；使用自定义 DomainRegistry 往返 decision；分别篡改 request fingerprint 列和 JSON schema 后读取。
- **修复**：模型前只投影 discovery v1 允许字段并重算 snapshot identity；SQLite 注入 registry，保存与恢复均通过 routing contract，逐项核对独立列，写入使用原子 `INSERT OR IGNORE` 幂等路径。
- **预防**：模型输入、模型输出和持久化恢复是三个独立的不可信接缝，必须分别执行 schema/allowlist 校验；测试同时覆盖第三 Domain、并发重复保存和损坏记录。

## FastAPI 与开发服务器复制自动路由状态机

- **现象**：两个入口都能通过局部测试，但 session 恢复、404 映射、async 分支和 interaction schema 各自维护，新增约束必须修改两遍。
- **根因**：把 transport handler 当成自动路由实现位置，复制了缓存、持久化、选择、改选和执行逻辑，没有建立公共 application seam。
- **诊断**：比较两个入口中 routing state 类、`/runs/auto` 分支和 response builder；若删除任一入口后复杂度不会回到公共模块，说明仍是浅封装。
- **修复**：收敛为 `DomainRoutingApplication`，HTTP 与 CLI 只调用 `catalog/select/override/run/clear_unbound_session`；Host 继续只消费已验证 `DomainSelection`。
- **预防**：新增入口先复用 application interface，再写传输契约；跨入口测试比较结构化结果，不复制内部状态机断言。

## 会话清理后自动路由缓存复活已删除决策

- **现象**：Domain 会话已 clear/delete，SQLite 中 decision 已删除，但同一进程仍可能通过旧 decision 继续执行；无持久化模式下，删除会话后旧 Domain binding 也可能继续生效。
- **根因**：持久层查询返回 `None` 后又回退进程内缓存；普通 Domain 会话生命周期只清理 Service/store，没有通知 `DomainRoutingState`。
- **诊断**：先保存并缓存 decision/binding，再从 store 或 Domain API 清理；分别验证旧 decision、clear 后 binding 和 delete 后 binding，不能只检查数据库行数。
- **修复**：配置持久层时以 getter 返回值为权威，包括 `None`；增加共享 `forget_session` seam，clear 清本地 decision 但保留 binding，delete 同时清理二者，FastAPI 与开发 HTTP 在 Domain 操作成功后统一调用。
- **预防**：任何持久化 + 缓存双层状态都要覆盖“底层删除、上层仍有值”的负向测试；clear 与 delete 的 identity 语义必须独立断言。

## 清空对话后迟到的恢复请求重新填充工作区

- **现象**：地图上下文已经 reset，但清空后中部结果又出现旧澄清答案和“暂无工具步骤”，用户看到的工作区并未真正清空。
- **根因**：页面启动或会话恢复请求与清空动作并发；旧请求完成后只校验 Domain/session，没有识别其所属的旧视图世代，因而继续调用 `renderRun`。
- **诊断**：让历史恢复保持在途，同时执行清空并检查 answer、steps、renderer context 和地图选择；仅验证 local state 为空不足以发现迟到 DOM 写入。
- **修复**：增加 `conversationGeneration`；清空、新建、删除、切换会话或重载 Domain 时递增，恢复与发送请求只允许在原世代仍有效时写入视图。
- **预防**：所有异步 UI 恢复都必须携带可失效的 view identity；清空 smoke 同时断言结构化上下文和可见工作区为空，并等待潜在迟到响应。

## Compose 的服务级 env_file 没有参与宿主数据卷插值

- **现象**：使用 `docker compose -f docker-compose.prod.yml up -d --build` 启动后容器 healthy，但 `/data` 为空，GIS runtime 降级；`.env.production` 明明配置了真实数据目录。
- **根因**：Compose 的服务级 `env_file` 只向容器注入环境变量，不参与解析 Compose 文件时的宿主机 volume 路径插值；未显式传 `--env-file` 时使用了默认空目录。
- **诊断**：用 `docker inspect` 核对 `/data` 的实际 `Source`，再在容器内只统计文件数和 runtime readiness；不要输出私有绝对路径、文件内容或密钥。
- **修复**：统一使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate`，确认 `/data` 文件数非零且 GIS runtime `ready`。
- **预防**：生产启动、重建和验收脚本都显式传同一 `--env-file`；服务 healthy 只证明进程存活，不能替代 volume identity 和 Domain readiness 检查。

## 路由证据在 run 复用与内部续跑边界可能漂移

- **现象**：同一 `run_id` 可被新的 routing decision 直接复用；用户确认或异步 worker 的 `_force_run_id` 续跑没有显式 evidence 时，已绑定 routing evidence 可能变成 unavailable。
- **根因**：routing identity 只在异步 job payload 中校验，Service 的同步幂等返回和内部续跑仍把 evidence 当作可选装饰字段，没有把它视为运行身份的一部分。
- **诊断**：对首次结果、同 ID 复用、强制续跑、SQLite 和 artifact 只比较 `{decision_id, request_fingerprint, selected_domain_id, binding.run_id}`；不要读取请求或模型响应。
- **修复**：同步复用先比较 routing identity，冲突 fail closed；内部续跑在调用方未提供 evidence 时从同 Domain 的既有 run 恢复并重新严格归一化；测试中的 Service 始终显式关闭。
- **预防**：新增任何 retry/confirm/recover/replay 路径时，都要证明 routing evidence 要么继承同一 identity，要么明确 unavailable，禁止静默替换；资源生命周期测试不得忽略 `ResourceWarning`。

## 公共 RequestFacts 省略原文导致 continuation 工作流丢失约束

- **现象**：首次能力选择正常，但用户从澄清或确认状态继续后，Text 摘要/统计/规范化工作流缺少 `text` 约束，生成的计划无法执行或行为与首次规划不同。
- **根因**：公共 RequestFacts 为脱敏和控制体积有意省略原文；续跑却把这个公共投影误当成 Domain Pack 的私有规划输入。
- **诊断**：比较首次规划与 `select_capability/provide_facts` 续跑进入 Domain workflow builder 的事实字段，确认持久请求仍存在但公共 facts 已省略正文。
- **修复**：Service 从已授权持久请求重新调用当前 Domain Pack 的 `extract_request_facts`；公共 Runtime 不解析领域字段，Text Domain 自己恢复文本约束。
- **预防**：公共证据投影与领域内部规划输入必须分离；任何 continuation 都从权威请求和 Domain extractor 重建私有事实，不能依赖为展示而裁剪的 RequestFacts。

## 新增 Console 模块未加入静态资源 allowlist 导致页面看似未变化

- **现象**：HTML 已引用新的 canonical interaction 模块，但浏览器加载后仍走旧交互或提示模块不可用，界面看起来完全没有生效。
- **根因**：生产 FastAPI 与开发 HTTP 都使用显式静态资源 allowlist；新增 JS 文件只写入仓库，未同时加入两个传输入口的允许列表。
- **诊断**：在浏览器 Network 中检查脚本是否 404，再分别检查 `production_api.py` 与 `serve_api.py` 的资源集合，不能只看本地文件存在。
- **修复**：把 `console_interaction.js` 同时加入生产和开发静态资源 allowlist，并按当前工作树重建镜像、禁用缓存后复验。
- **预防**：新增 Console 模块时把“脚本标签、两个静态 allowlist、Node 语法、生产镜像浏览器加载”作为一个原子检查。

## 前端 smoke 把动态动作 ID 固化在 Shell 源码位置

- **现象**：统一交互已能在浏览器完成选域，但 smoke 在打开页面前报 `index.html` 缺少 `select_domain`。
- **根因**：旧静态断言验证具体动作字符串出现在哪个文件，而不是验证 canonical contract 与 Action Host seam；动作目录迁入服务响应后，正确解耦反而被判失败。
- **诊断**：先区分静态 seam 失败和真实浏览器行为失败；检查测试是否搜索具体动作、局部函数或 DOM，而这些内容本应由结构化响应动态提供。
- **修复**：静态门禁改为检查 `renderCanonicalInteraction`、`ConsoleActionHost` 和版本化 interaction 模块；具体动作由浏览器 fixture 经 `interaction.actions` 注入并执行。
- **预防**：Shell 测试只锁定稳定 interface，不锁定 Domain/action identity 或实现位置；删除模块后若复杂度不会回到调用方，该断言就不应存在。

## pre-run 选域只有 child decision，没有持久 command receipt

- **现象**：重复选择同一 Domain 能复用 child decision，但响应没有动作回执；重启后无法证明幂等键、输入指纹和 result reference 与首次命令一致，并发 worker 还可能同时创建 sibling decision。
- **根因**：run action 已有 SQLite receipt/CAS，routing action 发生在 run 创建前，只用“先查 child、再保存 decision”的进程级流程模拟幂等，没有原子持久化命令身份。
- **诊断**：用两套独立 `DomainRoutingState/SQLiteConversationStore` 并发提交同一 parent/action，比较 child 数、receipt subject/result、幂等键和重启回放；单进程顺序重试不能证明跨 worker 安全。
- **修复**：在 `BEGIN IMMEDIATE` 事务中校验 parent/session，原子提交唯一 child 与 `action-receipt.v1`；receipt 的 subject/result kind 使用 `routing_decision`，相同 command 回放、不同选择返回 revision conflict。
- **预防**：任何发生在 run 之前的新 interaction action 也必须通过同一 command/receipt 语义；不能用“结果看起来一样”替代持久 idempotency identity。

## canonical Host 授权后仍读取 legacy allowed_actions 二次判断

- **现象**：`InteractionHost` 已根据最新 `interaction.actions` 验证命令，但 Service dispatcher 又读取 `selection_interaction.allowed_actions`；两套投影短暂漂移时，合法 canonical command 会被旧字段拒绝。
- **根因**：迁移时保留旧防线却没有区分授权与兼容展示，导致 legacy alias 仍处在活动策略路径。
- **诊断**：从 HTTP command 追踪到 Host 和 dispatcher，搜索所有 `allowed_actions` 读取；若动作在 Host 后再次根据 legacy selection 判定，就是重复授权。
- **修复**：dispatcher 只接收 Host 已验证的 normalized command；legacy selection 字段仅作为响应兼容投影。Console 异步状态也改读 canonical interaction，并删除旧 selection 模块与静态资源入口。
- **预防**：兼容 adapter 必须单向从 canonical contract 生成，不能反向参与授权、状态机或 UI 动作选择；阶段测试同时断言旧脚本未加载。

## Planner 上下文同时承担模型输入和完整证据导致 token 膨胀

- **现象**：复杂开放式 GIS 请求的模型调用耗时很长，原同步验收在 HTTP 客户端超时；Planner 上下文约 15.3K 字符，系统提示约 7.2K 字符，其中能力目录、工作流选择和模板重复描述同一能力。
- **根因**：`ContextPacket.payload` 同时作为 Planner 输入和 Runtime 证据来源；为了保留 Result/Evidence，只能把大块候选详情、动作目录、工具治理和模板内容一起送给模型。
- **诊断**：只比较 `context_evidence.section_chars`、Planner system prompt 长度、工具 schema 数量和 source evidence 是否完整；不要保存或输出模型原文、请求全文、密钥或私有路径。
- **修复**：新增 `planner_context` 投影 seam；`payload` 只保留有界 Planner projection，`source_payload` 保留完整证据来源。复杂请求模型上下文降至约 11.2K，系统提示按已选 workflow DAG/schema 去重至约 3.4K，9 个工作流工具 schema 全部可见。
- **预防**：公共 Result/Evidence 契约不能为了 token 预算裁剪；每个 Planner 输入投影都要有字段 allowlist、体积上限、schema 数量断言，并验证 source evidence、repair、SQLite/artifact 仍使用完整来源。

## 真实模型验收重复提交同步与异步 run

- **现象**：live 验收脚本先执行同步请求，再执行异步请求，模型被重复调用；同步请求可能先占满 HTTP 超时，即使异步路径本身可以成功。
- **根因**：脚本把“同步/异步独立运行一致性”误当成同一阶段的必需检查，导致真实模型成本和失败概率随验收步骤翻倍。
- **诊断**：统计验收报告中的 agent run 提交次数，并比较同一 run 的 polling、detail、artifact、evidence，而不是为传输一致性创建第二个模型 run。
- **修复**：`live_http_acceptance.py` 改为 async-first、auto-domain、单次提交；轮询终态后复用同一 run 的 detail/artifact/evidence。真实 DeepSeek + local GIS 复杂请求成功，结果类型为 `spatial_analysis_result`，单次 run 提交数为 1。
- **预防**：live 验收默认只做一次模型执行；独立稳定性对照必须显式单独命令并说明额外 token 成本，默认脚本不能隐式重复调用。

## GIS 数据目录完全缺失时后端初始化越过统一生命周期

- **现象**：`admin_areas` 没有文件时，`HybridSpatialBackend` 在 `AgentService` 创建 Runtime 阶段直接抛异常，HTTP 只能得到启动级错误，无法生成统一的失败证据、恢复动作和 artifact 状态。
- **根因**：Domain Pack 的 `tool_provider` 只考虑成功构造 native adapter；数据目录错误没有通过 ToolRegistry dispatch，因此没有进入 Runtime 的 provider failure contract。
- **诊断**：用不含真实文件的 dataset config 启动 local GIS，只输出 status、error_code、interaction state 和 action IDs；不能输出原始异常、绝对路径或数据文件内容。
- **修复**：新增通用 `UnavailableToolProvider`，GIS Domain 捕获本地后端初始化错误后保留已校验工具定义，调用阶段返回 `backend_initialization_unavailable`；Runtime 统一产生 `FAILED / recoverable` 和 `retry、recover、cancel`。
- **预防**：Domain adapter 初始化失败也必须落入 ToolRegistry/Runtime failure seam；缺失数据、未对齐和依赖不可用分别保留结构化 reason code，真实 GIS/live 验收与默认离线 smoke 分层。

## 兼容入口丢失 runtime_factory 导出导致历史验收无法导入

- **现象**：`tests.test_m62_spatial_intent` 等旧入口从 `run_demo import build_runtime` 导入失败，实际 Runtime 代码和功能正常。
- **根因**：`runtime_factory.py` 的模块说明仍承诺 `run_demo` re-export，但重构后根入口只保留 CLI 逻辑，兼容 seam 未同步维护。
- **诊断**：先运行测试收集阶段和 `rg "from run_demo import build_runtime"`，区分导入兼容故障与业务断言故障。
- **修复**：恢复 `run_demo` 对 `agent.runtime_factory.build_runtime` 的显式兼容导出；不恢复旧的内部实现或增加重复 Runtime 工厂。
- **预防**：移动模块后保留的兼容入口要有一个最小 import smoke；历史测试精简时优先修复真实公共 seam，再删除重复矩阵。

## 浏览器视觉验收进程初始化异常退出

- **现象**：Docker 首页和 HTTP 验证正常，但通过 Browser 技能连接本地 `http://127.0.0.1:8088/` 时，浏览器控制进程在初始化阶段异常退出并自动重置会话；运行既有 CDP smoke 时访问 `http://127.0.0.1:9222/json/list` 直接 `fetch failed`，无法取得页面截图或交互状态。
- **根因**：当前执行环境的浏览器控制运行时/浏览器连接层初始化失败；现有证据不足以归因于前端页面代码，且不是服务返回错误。
- **诊断**：先检查容器健康状态和 HTTP 200，再运行 Node 语法、Console smoke 和 Docker 契约；单独有界探测 `9222/json/list`，区分“没有 CDP 页面”与“页面脚本断言失败”；浏览器连接失败时不要反复启动多个控制会话，也不要把它报告为页面回归。
- **修复**：本轮使用精简静态检查、前端 smoke、Docker 契约和 HTTP 内容断言完成代码验收；浏览器视觉检查保留为显式待补验收，不修改业务代码绕过浏览器运行时。
- **预防**：浏览器 smoke 启动前做有界连接探测；连接层异常时记录环境阻塞并回退到离线/HTTP 证据，恢复后使用干净会话重新验证首屏、对话输入和结果空态，避免并发复用旧 CDP 会话。

## M230 全局 Goal 验收审计记录

- **范围**：按 Goal 的 9 项核心要求和 8 项验收标准，核对当前代码、Docker 镜像、离线门禁、真实模型/GIS、artifact/restart 和浏览器渲染证据。
- **证据**：M229 真实 HTTP run 为 `spatial_analysis_result`，单次提交并完成 polling/artifact/evidence；重启后 existing-run 校验通过；Console 动态恢复 raster、composite、map workspace；CLI complex local run 成功并导出 artifact；Text Domain、核心 contract、repair、能力澄清和 `grid_mismatch` gate 的分层测试通过。
- **边界**：真实模型只在显式 live 路径调用，不进入默认 CI；报告不保存请求全文、模型原文、密钥、原始数据或宿主路径。默认 Docker 测试保持 quick/stage/smoke 分层。
- **结论**：Planner/Runtime、ToolRegistry、Domain Pack、结构化契约、统一生命周期、跨入口恢复、动态前端、通用能力扩展和风险分层测试均已达到当前 Goal 的验收要求。后续功能扩展应创建新 Goal，避免在本 Goal 中继续堆叠领域细节。

## Console 自动领域会话入口与全量清理缺失

- **现象**：自动领域尚未绑定时，“新建会话”被初始化逻辑禁用；页面没有“清空全部对话”入口；切换本地草稿会话时可能误请求 `/domains/auto/...`。
- **根因**：会话按钮状态只按“已绑定真实 Domain”判断，未把未绑定状态视为可操作的本地草稿；前端只实现了当前会话的 clear，没有统一遍历 Domain 会话并删除的动作；会话切换始终进入持久化恢复路径。另一个关键错误是直接把 `newSession` 作为 click handler，原生 `Event` 被当成 `domainId` 后触发早退，导致按钮点击无请求、无报错、无 UI 变化。
- **诊断**：浏览器 smoke 先清除自动路由 localStorage 和旧 session 选项，再断言新建按钮可用、会话选项增加并切换；随后只清理 smoke 自己创建的本地草稿，检查消息和结果工作区重置。避免默认 smoke 调用全量删除 API。
- **修复**：未绑定自动领域使用本地 draft session；已绑定领域通过当前 Domain 的 `/sessions` 创建持久会话；事件绑定改为 `()=>newSession()`；新增带确认的“清空全部对话”，固定领域清理当前 Domain，自动领域遍历注册 Domain，并在失败时保留结构化错误摘要；清空先获取待删清单并立即重置前端，再执行删除；增加 session catalog generation，阻止旧目录请求迟到回填；最后保留一个可用空白会话。
- **布局调整**：将“准备好执行任务”改为紧凑状态条，标题与决策状态并排；桌面右侧对话工作区使用更宽的列和按视口高度的长面板，输入区保持在底部；移动端保留原有单列规则。
- **预防**：会话 smoke 不得依赖浏览器残留绑定，也不得默认删除真实持久会话；全量清理动作必须有用户确认、逐项失败汇总和可用空白会话；UI 尺寸回归同时检查顶部状态卡上限和对话面板最小高度。

## 阶段提交完成但 GitHub 推送被网络阻塞

- **现象**：本地阶段提交已经成功，但 `git push` 访问 `github.com:443` 超时，不能据此宣称 GitHub 版本已更新。
- **诊断**：先检查 `git status`、最新 commit 和本地 diff，再在允许的宿主网络权限下重试一次；区分代码、认证和出站网络故障，不修改 remote、不提交密钥，也不反复重试造成噪声。
- **当前处理**：初始 commit `e792a08` 曾因网络阻塞留在本地；网络恢复后，包含后续修复的 `c0a2780` 已成功推送到 `origin/main`。Docker、契约测试和浏览器 smoke 均已通过。
- **预防**：阶段汇报同时标记“本地提交”和“远端推送”两个状态；只有收到 push 成功响应后才记录为 GitHub 版本，恢复上下文后优先重试未完成的 push。

## 聊天输入区在首屏不可见

- **现象**：页面打开后右侧聊天框可以看到消息区，但底部“发送”按钮不在首屏；窄栏中预览和发送还会纵向占用更多高度。
- **根因**：聊天框位于顶部状态卡之后，却使用接近完整视口高度的固定高度，初始位置叠加状态卡后把底部输入区推到视口以下；输入按钮区同时使用纵向两行布局，不适合窄的桌面侧栏。
- **诊断**：先检查页面首屏结构和 CSS 计算关系，确认聊天列位于状态卡之后，再检查聊天内部是否有明确的可伸缩消息区和固定输入区；不要通过隐藏消息或缩小可读文本来“挤出”按钮。
- **修复**：桌面采用“结果工作区 + 右侧聊天列”两列布局；聊天容器使用 flex 垂直布局，消息区 `flex: 1` 且 `min-height: 0`，输入区固定为不可压缩底栏；高度按状态卡之后的剩余视口计算，并将预览/发送按钮改为横向并列。发送按钮显式声明 `type="button"`。
- **预防**：新增或调整顶部状态卡、设置栏时，必须同时检查聊天输入区的首屏可见性；固定侧栏不得以完整视口高度计算而忽略自身在页面中的起始位置，桌面首要操作按钮必须有清晰的固定落点。

## 领域动作展开层被消息区遮挡

- **现象**：桌面端点击“领域动作”后，动作窗口展开但被下方对话消息区覆盖，或超出设置栏后被聊天容器裁剪。
- **根因**：展开层仅设置了局部 `z-index`，设置栏和消息区没有明确的层级关系；聊天容器使用 `overflow: hidden`，同时弹出层定位依赖固定偏移，无法适应设置栏换行后的实际高度。
- **诊断**：检查弹出层的最近定位祖先、设置栏与消息区的 stacking order，以及父容器是否裁剪 overflow；区分“层级被覆盖”和“内容被裁剪”两个问题。
- **修复**：设置栏建立更高层级，动作窗口相对设置栏自适应定位，使用视口约束的最大高度和内部滚动；聊天容器允许必要的视觉溢出，消息列表继续由自身滚动区域负责裁剪。
- **预防**：所有浮层都必须明确定位上下文、层级和最大尺寸；不能只添加更大的 `z-index` 而忽略祖先的 overflow 裁剪，也不能使用固定像素偏移替代动态定位。

## GIS 栅格预览被误画成规则实心矩形

- **现象**：综合空间分析已有部分 GeoJSON 要素，但地图仍显示一整块规则矩形“栅格覆盖范围”，看起来像伪造的分析区域。
- **根因**：GIS view builder 只接受 `real_geometry` 或 `boundary_geometry` 的 GeoJSON；当摘要被截断但仍有 GeoJSON artifact 时，错误回退到第一份 DEM bounds。前端 `raster_bounds` renderer 又用实心 `<rect>` 表示该 bounds，造成外接范围与有效像元覆盖混淆。
- **诊断**：用 `truncated_geometry + geojson_ref + raster bounds` 的最小 result contract 重现，检查 map view 是否仍为 `raster_bounds`；再单独检查 renderer fallback 是否把 bounds 渲染成实心矩形。
- **修复**：`truncated_geometry` 只要保留 GeoJSON artifact 就继续走 GeoJSON renderer，显示可用的部分真实几何；没有 artifact 时才显示虚线外接范围，并在无障碍标签和图内标题中声明“非有效像元边界”。
- **预防**：外接范围、有效像元 footprint、候选区域和部分 GeoJSON 必须使用不同的结果语义；不能仅凭 bounds 生成看似真实的填充区域，也不能因摘要截断而丢弃仍可恢复的几何 artifact。

## 结构化结果和 Agent 回答直接暴露内部表示

- **现象**：结构化结果中的最大值、最小值保留过长小数；分布对象被前端转换为 `[object Object]`；综合回答直接展示 `ready`、工具步骤、数据集标识和内部执行数量，普通用户难以理解。
- **根因**：通用 renderer 对值直接调用字符串转换，未区分标量、嵌套对象和分布数据；Domain Composer 以前把执行轨迹摘要当作最终回答，没有独立的用户表达层。此前没有把“模型生成回答”和“确定性兜底回答”区分为两个边界。
- **诊断**：用最小 view 同时放入长小数、嵌套分布和 rows 对象，检查 DOM 是否出现精度过高或 `[object Object]`；用结构化 GIS 步骤构造回答，确认不应出现 `ready`、工具名或内部引用。
- **修复**：展示层统一做有限小数、千分位和大数格式化；分布使用样本数、区间、数量和比例的有界列表；地图范围在支持的 CRS 下交给 Leaflet 用真实 bounds、比例尺和 fitBounds 定位；确定性回答改为“结论—主要发现—注意事项”，内部证据继续放入高级详情。
- **预防**：最终用户回答应优先经过独立 Answer Generation seam：先生成有界结构化事实，再由真实模型生成自然语言并校验长度、引用范围和禁用内部字段；模型不可用或规则测试模式下回退到 Domain-owned 模板。不能把原始工具结果、模型原文或执行轨迹直接展示给用户，也不能用更多 GIS 专用句式替代公共表达层。

## distance 空间算子在大范围 mask 上不必要地构造全量 union

- **现象**：真实道路与水体距离分析在大数据量下超时，调用尚未进入稳定的距离统计阶段。
- **根因**：`clip`、`intersect`、`buffer` 和 `distance` 共用实现时，distance 也先把整个 mask 图层 union；距离计算实际上只需要投影后的空间索引最近邻查询。
- **诊断**：用真实本地 GIS 运行明确的距离阈值问题，区分工具超时与模型规划超时；只比较要素数、CRS、距离摘要和截断状态，不读取原始几何。
- **修复**：distance 路径改为投影后 `geopandas.sjoin_nearest`，按输入索引聚合最近距离；仅 `clip/intersect/buffer` 构造 mask union，继续保留 `max_distance`、CRS、预算和结果引用契约。
- **预防**：通用空间算子新增操作时先确认是否真的需要全量几何聚合；真实大数据验收必须有明确阈值、预算和安全摘要，不能只用小 fixture 推断性能。

## 真实 GIS 验收问题过于宽泛，无法证明业务意图

- **现象**：用“计算道路与水体的最近距离”做验收，没有区域、对象筛选条件或阈值；道路与水体相交产生 0 米是合法结果，但无法判断是否符合需求。
- **根因**：把算法 smoke 当成业务验收问题，缺少分析区域、目标对象、空间关系和预期输出的最小定义。
- **诊断**：验收问题至少检查区域/数据对象、筛选阈值、统计指标和缺字段时的处理；若这些信息不完整，只能作为底层算子 smoke，不能作为 Agent 业务能力结论。
- **修复**：改用“在洪山区范围内分析道路与水体相邻关系，先按边界裁剪道路，再筛选距离水体不超过 100 米的道路段并输出最小/平均/最大距离；字段缺失时说明”的明确问题；0 米在该阈值筛选中按真实事实保留，不做异常修正。
- **预防**：每条 live 验收先写清目标、区域、输入、约束、输出和降级条件；开放式问题应验证 Planner 的组合能力，底层性能测试则直接标注为 operator smoke。

## 真实模型规划超时与 GIS 工具执行失败被混为一谈

- **现象**：明确的空间请求 live run 最终失败，但失败记录显示 0 个工具步骤和 `provider_timeout`；如果只看最终 FAILED，容易误判为 GIS distance 实现失败。
- **根因**：模型规划调用和本地 GIS 工具执行共享外层运行结果，但诊断时没有先根据步骤数和错误分类区分阶段。
- **诊断**：先看 `status`、`error_category/code` 和已执行步骤数量；规划阶段 0 步且为 provider timeout 时，不继续修改 GIS 代码，也不输出模型原文或配置。
- **修复**：真实模型请求只保留脱敏的规划失败证据；用同一 Docker/真实数据的 Rule Planner 隔离验收 GIS，确认 distance 已完成后再归类为模型/网络环境问题。
- **预防**：live 报告必须分别记录 planner、tool execution、artifact/recovery 阶段；模型失败不自动重跑多条昂贵请求，GIS 性能结论必须有独立的非模型验收证据。

## 有限 replan 完成降级结果时用户回答没有说明原任务未完成

- **现象**：行政区名称未匹配到几何，`spatial_operation` 失败后 Rule Planner 降级到数据健康摘要；外层状态为 `COMPLETED`，但回答只说“数据检查完成”，用户容易误以为裁剪成功。
- **根因**：Runtime 允许保留失败步骤作为 repair lineage 并完成替代计划，这是合法的恢复语义；公共回答出口却没有把“降级完成”和“原始目标完成”区分开。
- **诊断**：检查最终计划类型、失败步骤、replan lineage、结果契约 degradation 和回答；不得因缺几何而伪造边界或把健康摘要改名为空间结果。
- **修复**：保留有限 replan 的 `COMPLETED`/降级结果契约，在 Runtime 的统一回答出口追加“原计划部分步骤未完成、当前为降级结论、修复后可重试”的短提示，并增加回归断言。
- **预防**：恢复状态的成功必须同时表达替代结果和原目标覆盖范围；所有 Domain Composer/Answer Generator 都经公共回答出口，失败 lineage 不能只放在高级执行详情里。

## 通用 workflow constraint 不支持区域列表

- **现象**：新指标 Domain 需要把多个区域传给同一个工具，但模板编译器只允许 string/number/integer/boolean/enum，区域数组无法通过标准 workflow seam。
- **根因**：早期模板主要覆盖单值 GIS 约束和 Text 输入，没有把有界列表作为领域中立约束类型建模；如果 Domain 绕过编译器，会破坏统一的计划校验和证据。
- **诊断**：先在 `workflow_template_context` 阶段检查模板 schema，而不是只直接调用 Provider；验证输入数组的最小/最大长度、元素类型和最终 ToolRegistry 参数形状。
- **修复**：公共 workflow compiler 增加 `array` constraint，支持有限长度和非空字符串元素，最终仍走同一模板、DAG、TaskPlan 和 ToolRegistry 校验。
- **预防**：新增 Domain 需要集合参数时优先扩展公共约束类型；所有列表必须有界，不能通过字符串拼接或 Domain 私有绕过层传参。

## 多区域自然语言解析被贪婪正则合并

- **现象**：请求“区域甲和区域乙的趋势”被解析为一个名为“区域甲和区域乙”的区域，Provider 返回无匹配数据。
- **根因**：区域正则使用贪婪字符类，没有识别“和/与/顿号/逗号”等自然分隔符；这类错误只在多对象请求中出现，单区域测试无法发现。
- **诊断**：同时用单区域、双区域和三区域短句检查 `RequestFacts.entities.regions` 与最终工具参数；只比较结构化 identity，不保存请求原文到验收报告。
- **修复**：按常见自然分隔符截断区域 token，并保留通用“市/区/县/区域”后缀识别；增加双区域趋势回归。
- **预防**：开放式 Planner/Domain extractor 测试至少覆盖一个多对象组合；解析器不能把示例区域名固化成唯一 allowlist。

## 指标 Domain 的 demo fixture 被误当成真实结论

- **现象**：新指标链路可以执行并返回 metrics/timeseries/composite，但默认数据只是架构演示数据，不能支撑武汉/洪山现实判断。
- **根因**：为了先验证 Runtime seam 使用了内置小 fixture；如果没有 provenance 和验收分层，用户可能把演示值当成真实统计。
- **诊断**：检查结果 `provenance.source`、数据健康状态和 `SPATIAL_AGENT_INDICATOR_DATA` 配置；不要以“运行成功”替代来源真实性验证。
- **修复**：fixture 的 attribution 明确写明“不代表真实统计数据”，Provider 支持环境变量注入配置文件；真实公开数据适配、来源校验和跨入口恢复留到 M252。
- **预防**：任何 Domain 的默认样例都必须带来源/版本/许可摘要，并在 live/real-data 报告中与 offline fixture 分开；未完成来源验收时不得宣称经济或区域结论。

## 当前代码结构已逻辑分层但物理边界尚未收敛

- **现象**：Domain Pack 已承载 GIS、Text 和指标实现，但 `agent/` 仍保留较多兼容 facade、legacy 字段和回退入口；`agent/service.py` 与 `agent/runtime.py` 仍分别约 3,409/2,567 行、87/74 个函数。HTTP 仍同时维护 FastAPI `production_api.py` 和标准库 `serve_api.py` 两套传输映射；前端 `web/index.html` 约 198 KB，内联 CSS/JS 仍然过大。
- **根因**：多轮迁移优先保证旧 artifact、旧导入、开发环境和生产入口可恢复，真实实现已经下沉，但兼容投影、应用编排、传输适配和展示代码没有同步完成最后一轮物理收敛。图片中的“133 处 legacy”不是当前唯一可靠口径；当前静态宽匹配在 `agent/` 得到约 233 行，且包含有意保留的 schema/历史数据兼容说明，不能直接全部删除。
- **诊断**：先区分活动路径、单向兼容投影和真实重复实现；检查 `AgentService`/`AgentRuntime` 的职责簇、两个 HTTP 入口的共享 `api_contract` 使用情况、生产代码中的 `*_contract.py`/`*_evidence.py` 归属以及前端 renderer/plugin 的加载关系。当前生产源码（排除 tests/archive）有 8 个 contract 文件、10 个 evidence 文件；`print` 当前约 26 处且主要位于 CLI/scripts，并非库代码 73 处。`except Exception` 当前约 50 处，必须按恢复边界逐处判断，不能机械替换。
- **处理计划**：新增能力前先做架构收敛切片：一是建立 canonical Application/Runtime、HTTP transport adapter 和 Domain facade 的活动路径清单；二是按深模块职责拆分 Service/Runtime，保留小型兼容入口；三是把重复的 bounded/normalize/status 基础逻辑收敛到公共 helper，但保留领域证据语义；四是将 Console HTML、CSS、启动编排和 renderer/plugin 继续物理拆分；五是清理可确认的 CDP 临时目录和无引用兼容模块。每次删除都要有最小 import、跨入口 contract 和 artifact/recovery 回归证据。
- **预防**：兼容层必须单向从 canonical contract 投影，不能重新参与业务决策；两个 HTTP 入口只能共享同一个应用用例和 payload/result contract，不得各自复制业务分支；新增 `contract`/`evidence` 文件前先判断是否能复用已有深模块；静态规模指标只能作为风险信号，不能替代活动路径和删除安全性审计。

## GIS 空间关系 View 引用未定义变量导致 CI smoke 失败

- **现象**：GitHub CI 的 Stable contract gate 在 `scripts/test_profile.py --profile ci` 的 service smoke 阶段失败；道路/坡度请求执行到结果契约构建时抛出 `NameError: name 'operation' is not defined`，导致用户请求无法完成。M251 指标测试和核心 contract tripwire 本身仍通过。
- **根因**：M250 增加空间算子 View 时，把 `operation` 相关的标签判断复制到 `_spatial_relation_view()`；该 View 的输入是 `spatial_join` 关系结果，不保证 `operation` 参数，且该局部变量在返回结构中也没有被使用。
- **诊断**：先从 GitHub run 的 job/step 状态确认失败发生在 `test_profile.py --profile ci`，再在 Docker 中运行同一命令；用不含 `operation` 字段的最小 `spatial_relation_result` View 直接复现红色回归，区分 GIS 执行失败与 Result/View 投影失败。
- **修复**：删除 `_spatial_relation_view()` 中无效且未使用的 `operation` 引用；保留 `spatial_operation` View 自己对 operation 的标签处理。新增最小 View contract 回归，修复前失败、修复后通过；原始 service smoke、CI profile 和 compileall 均恢复通过。
- **预防**：Domain View builder 必须用对应 result type 的最小输入分别验证；复制字段标签逻辑时不能假设相邻 View 共享参数。CI smoke 失败时先执行同一 profile，再按错误阶段区分规划、工具执行、Result contract 和前端投影。

## GIS Adapter 物理迁移遗漏相对导出模块

- **现象**：GIS backend 已迁入 `domains/gis/adapters` 后，GeoPackage 空间操作在导出结果时抛出 `ModuleNotFoundError`，而其他空间操作测试仍可通过；同时旧边界测试仍断言已删除的 `agent.spatial_backend` 实现路径。
- **根因**：迁移按 backend 文件分组时遗漏了被多个执行分支延迟导入的 `geometry_export.py`；测试断言绑定了迁移前的实现位置，而不是 canonical adapter seam。
- **诊断**：先运行 M252 Domain boundary 与 M247 spatial operation 定向回归；对失败堆栈区分延迟相对导入缺失和测试静态断言过时，不用直接导入 facade 掩盖真实活动路径。
- **修复**：将 `geometry_export` 真实实现迁入 `domains/gis/adapters`，`agent.geometry_export` 改为单向兼容 facade；边界测试改为断言 `spatial.py` 使用 `dataset_catalog`/`spatial_backend` 相对导入且不依赖 `agent.*`。
- **预防**：物理迁移前搜索顶层和函数内的相对导入、动态导入与 re-export；每批迁移必须覆盖定向 Domain boundary、真实 adapter 执行/导出和架构静态守卫，不能只验证导入成功。

## Docker 旧容器内容导致架构验证与工作树不一致

- **现象**：宿主工作树已新增 adapter 文件和测试修复，但容器仍缺少新文件；第一次定向测试继续报旧错误，`compileall` 还发现旧容器残留的嵌套 `adapters` 目录和不可写缓存目录。
- **根因**：生产 compose 使用镜像 `COPY . /app`，容器不是宿主源码实时挂载；仅修改宿主文件不会更新运行中的容器，手工复制又可能留下旧目录状态。
- **诊断**：对比宿主 `rg --files domains/gis/adapters` 与容器 `/app/domains/gis/adapters` 文件清单；若测试堆栈仍是已修复的旧内容，先判断容器同步问题，不回退代码。
- **修复**：使用 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build` 从当前工作树重建并健康检查，再在干净容器执行 compileall、定向回归和 quick/stage。
- **预防**：所有结构迁移完成后必须重建 Docker 镜像再验收；文档明确“容器复制/镜像”与“实时挂载”区别，禁止把临时 `docker cp` 当作阶段交付同步方式。

## Application seam 迁移把 Service 局部别名误当成源函数名

- **现象**：`AgentService` 引入 `RunApplication` 后，模块加载阶段连续出现 `ImportError`，提示 `service_format` 中不存在 `_exported_geometry_evidence` 和 `_tag_geometry_features`。
- **根因**：旧 Service 使用 `exported_geometry_evidence as _exported_geometry_evidence`、`tag_geometry_features as _tag_geometry_features` 的局部别名；迁移代码复制了别名名，却没有复制源函数的导入映射。
- **诊断**：对导入失败的符号回到源模块检查真实定义，再对比旧调用方的 import alias；不要通过在源模块新增私有别名来掩盖迁移边界问题。
- **修复**：Application module 从 `service_format` 导入真实函数并在本地使用 `as` 建立兼容别名；Docker 重建后 M78 facade import、Runtime/Domain 定向回归恢复通过。
- **预防**：拆分模块时分别核对“源模块导出名”和“调用方局部别名”；迁移完成后先运行只覆盖模块导入和 facade public method 的最小契约，再运行完整行为回归。

## 生产 Docker 的持久状态环境污染内存 Session 测试

- **现象**：M68 内存 session 测试期望第一次创建为“对话1”，但在生产容器直接运行时收到“对话2”；同一组代码在不使用持久 DB 的环境中通过。
- **根因**：生产 Docker 通过 `SPATIAL_AGENT_STATE_DB` 指向 `/app/outputs/spatial-agent.db`，而内存测试调用 `AgentService()` 时会读取该环境变量，因此复用了前序测试或服务运行留下的 SQLite session。
- **诊断**：比较测试进程的 `SPATIAL_AGENT_STATE_DB` 与测试预期；生产 API 的健康运行验证应保留 DB，而 memory session 单测应在容器内显式 unset 该变量。不要删除容器输出或污染真实状态库来“修复”断言。
- **修复**：使用 `docker exec ... sh -lc "unset SPATIAL_AGENT_STATE_DB; python -m unittest ..."` 运行内存 session 契约；SQLite session 测试继续使用自己的临时数据库。生产 quick/stage 仍使用 compose 的 `.env.production`。
- **预防**：测试 profile 明确标注 memory/persistent 两种状态模式；依赖默认 `AgentService()` 的内存测试必须由 runner 清除持久状态环境，不能假设生产容器环境天然是空内存。

## 异步 Session 回归用固定短轮询窗口误判未完成

- **现象**：异步接口已经正确返回 `QUEUED` 和 `run_id`，但回归测试在固定约 0.6 秒的轮询结束后得到 `PLANNING`，将正常的慢执行误报为失败。
- **根因**：测试把异步执行速度当成状态契约；Docker、GIS 依赖初始化或机器负载变化会让合法的 worker 完成时间超过短窗口，生产状态机本身并未改变。
- **诊断**：先确认初始响应为 `QUEUED`，再单独运行该测试并记录终态；如果扩大有界等待后稳定得到终态，应归类为测试时序问题，不要为了让测试立即完成而修改异步 worker。
- **修复**：使用 `time.monotonic()` 加有界总超时轮询 `PLANNING`/`EXECUTING`，同时保留最终 `COMPLETED`/失败状态断言；不使用无限等待或固定次数替代时间语义。
- **预防**：异步测试必须验证“先受理、后终态”的生命周期，而不是假设某个固定毫秒数内完成；默认测试保持秒级上限，live/性能测试另行分层。

## Action 输入校验测试与执行失败码不一致

- **现象**：GIS action 的数组 `minItems` 校验失败时，旧回归断言要求 `action_execution_failed`，而公共 action contract 返回 `action_invalid_input`；同一套 action replay 因此看起来像首次执行和回放不一致。
- **根因**：测试把“Domain handler 执行异常”和“进入 handler 前的 schema 校验异常”混为一类；`ActionApplication` 会保留具体的校验错误码，并在 artifact/execution record 中传播。
- **诊断**：区分 `action_execution.input_validated`、`error_code` 和 `action_error_code`，同时比较首次异常、幂等回放和 artifact；不要为了通过历史断言把合法输入错误改成通用执行错误。
- **修复**：统一校验失败的测试契约为 `action_invalid_input`，保留 `action_execution_failed` 仅用于 Domain handler 或持久化执行阶段的失败。
- **预防**：新增 action 测试至少覆盖 schema rejection、Domain execution failure 和 replay 三种路径；公共错误码应与失败阶段对应，不能只按最终 HTTP 状态归类。

## 前端重构后静态测试仍锁定旧 URL 拼接

- **现象**：Action Domain 的运行、artifact 恢复和历史功能正常，但旧静态测试仍要求页面包含 `nativeFetch('/actions'+query)` 或固定 `/artifacts/actions/` 字符串，导致 action 回归失败。
- **根因**：前端已经统一通过 `domainPath`、`artifactReferencePath` 处理领域作用域和 artifact 链接，静态测试却锁定了迁移前的字面拼接方式。
- **诊断**：先用 `rg` 对比测试 token 与当前 renderer/transport seam，再用 HTTP action/artifact 回归确认运行行为；不要为了满足旧 token 恢复领域无关的 URL 拼接。
- **修复**：断言稳定的 helper seam（`domainPath`、`artifactReferencePath`、`renderActionEvidence`）和用户可见契约，删除过时的字面 URL 断言。
- **预防**：前端静态测试锁定模块 seam、数据属性和行为入口，不锁定可替换的 URL 拼接细节；页面重构后同步清理 compact 测试，避免把历史实现当成契约。

## 交互 dispatch 使用未投影的当前 interaction

- **现象**：交互读取和普通运行可以成功，但 `select_capability`/`provide_facts` 进入 dispatch 时抛出 `NameError`，HTTP 交互返回 500，action receipt 无法形成。
- **根因**：dispatcher 读取了当前 run 和 result envelope，却没有调用公共 `project_interaction` 生成局部交互投影；代码只在需要能力选择的分支才触发该隐藏错误。
- **诊断**：用最小的能力选择交互覆盖应用、HTTP、artifact/restart 四条路径；看到 500 或缺失 receipt 时先检查交互投影是否在 dispatch 入口完成，不要修改 Domain capability resolver。
- **修复**：在 dispatcher 读取当前 run 后立即构造 `interaction = project_interaction(current)`，后续能力选择和事实补充均使用同一投影。
- **预防**：交互 dispatch 的入口必须先完成一次 canonical interaction projection；新增 action 分支不得依赖未声明的隐式局部变量，并至少保留一条具体 selection action 回归。

## HTTP 迁移后静态契约仍锁定旧的 transport 导入

- **现象**：HTTP dispatcher 已将 workflow、payload 和 read/write 语义移入 `HTTPApplication` 后，M78 静态测试仍要求 `serve_api.py` 直接导入 `workflow_action_result`；生产行为和 HTTP contract 正常，但测试失败。
- **根因**：测试把旧 transport 的实现细节误当成共享契约。新的深模块 interface 是 `HTTPApplication.execute/read`，transport 不应继续复制 workflow 或 read projection。
- **诊断**：先检查失败测试断言的 token 是否仍位于活动路径，再用 FastAPI、标准库 HTTP 和 application contract 验证用户可见行为；不要为满足静态 token 恢复已删除的旧导入。
- **修复**：将测试改为断言 `HTTPApplication` seam、共享 error mapping 和稳定 payload contract；保留 `api_contract` 仅用于仍由 transport 使用的错误投影。
- **预防**：HTTP 重构后，静态测试应锁定 canonical application seam 与行为，不锁定旧 helper import、URL 拼接或分支位置；每次 read/write 迁移都运行双入口 contract 和 artifact/Domain 路由回归。

## 前端 CDP smoke 依赖未启动导致误判代码失败

- **现象**：Docker API healthy、页面可访问，但 `console_map_smoke.js` 首次运行因 `ECONNREFUSED 127.0.0.1:9222` 失败；随后启动项目的 CDP 测试入口后 smoke 正常。
- **根因**：该 smoke 连接本机 Chrome DevTools Protocol，不会自动启动浏览器；它与 Docker HTTP 服务是两个独立依赖。
- **诊断**：先确认容器 healthy 和 `/health` 200，再检查本机 9222 是否监听；区分 API/页面故障与浏览器驱动未启动，不要修改前端或后端来规避连接错误。
- **修复**：运行 `scripts/console_cdp_start.ps1` 启动隔离 Chrome profile，再串行执行 map、session、new-session 和 selection smoke。
- **预防**：浏览器验收脚本应在文档/runner 中显式声明 CDP 前置条件；默认 CI 继续保持离线精简，浏览器 smoke 作为显式验收路径运行。

## Evidence recovery 浅层模块与 canonical projection 版本漂移

- **现象**：同步、异步、artifact 和 HTTP 都能返回 evidence，但 recovery 逻辑位于独立薄模块；新增字段或 schema 版本时容易只更新 projection，遗漏 recovery，造成跨入口差异。
- **根因**：`evidence_recovery.py` 只有一次 `project_evidence_projection()` 调用和状态映射，没有独立的数据来源或 adapter；同时 async/replanning 版本曾在多个模块重复声明。
- **诊断**：搜索所有 `project_evidence_recovery`、schema version 声明和 import 路径，比较同步 Result、async evidence、artifact viewer 与 HTTP evidence 的嵌套字段；不要仅按文件名判断是否存在独立职责。
- **修复**：将 recovery 投影并入 `agent.evidence_projection` 的 canonical seam，旧模块只保留兼容 re-export；版本常量分别复用 `contract_versions` 或其所属 registry 的唯一声明。
- **预防**：只有具有独立输入、状态机或 adapter 的 Contract/Evidence 模块才保留单独 seam；薄投影优先并入深模块，并用活动路径静态断言、artifact/async/HTTP 对等回归锁定兼容行为。

## M258 前端源码拆分后静态契约仍读取兼容入口

- **现象**：把 Console 从单一 `web/index.html` 拆成 `web/src/index.html`、`styles.css`、`console_app.js` 和 renderer/plugin 源码后，页面与 HTTP 资源可正常访问，但历史静态测试找不到原来写在 HTML 内联脚本中的函数、证据标记和交互 token。
- **根因**：测试把“页面源码文件”误当成“完整前端应用契约”；同时 HTTP 的 FastAPI 与标准库入口各自维护静态资源根目录和 allowlist，导致源码、构建产物和兼容路径之间可能漂移。
- **诊断**：先确认 `web/src` 是否是唯一实现、`web/dist` 是否由当前工作树构建，再区分三类检查：HTML 结构检查只读 `index.html`，应用行为检查通过统一 source reader 组合 shell/CSS/app，Node smoke 直接加载 canonical module；最后分别请求 `/`、`/styles.css` 和 `/console_app.js`。
- **修复**：新增无依赖、确定性的 `scripts/build_console.py`，Docker 构建时生成 `web/dist`；新增 `agent.web_assets` 作为两个 HTTP transport 共用的静态资源 seam，未构建时回退到 `web/src`；根 HTML/JS 仅保留单向兼容 facade，静态测试迁移到 canonical source helper。
- **预防**：源码物理拆分后，测试不得重新把实现拼回生产 HTML，也不得锁定旧根路径；新增前端模块必须登记到 `agent.web_assets`、构建器和最小 Node smoke，阶段验收必须重建 Docker，确认容器内服务的是 `web/dist`。兼容 facade 只允许单向转发，不能承载第二份实现。

## M259 Runtime 状态与能力目录混在编排模块

- **现象**：Runtime 同时持有内存运行状态、澄清会话、能力目录、工作流契约、运行时能力快照、发布证据和 capability evidence cache；即使执行路径已有 projection/planning/execution/control seam，`runtime.py` 仍持续膨胀，架构检查只能报告 god-module。
- **根因**：这些职责都从 Runtime 被调用，但它们的输入、生命周期和变化原因不同；把“被同一个入口调用”误认为“必须放在同一个实现模块”，造成状态 adapter、能力 evidence 和编排生命周期互相耦合。
- **诊断**：先按变化原因和持久化需求分组，而不是按调用者分组；检查 Runtime 是否直接创建锁、缓存、状态字典，是否直接组合 Domain capability/release provider；再用活动路径回归确认迁移前后 public import、SQLite 导入和 capability snapshot 形状一致。
- **修复**：新增 `agent.runtime_state` 作为内存状态/澄清 adapter seam，新增 `agent.runtime_core.capabilities.RuntimeCapabilitySurface` 作为能力目录与运行时证据 seam；Runtime 只保留兼容入口并注入小接口，`sqlite_store` 改从 state seam 导入。
- **预防**：新职责必须先判断是否拥有独立状态、provider 或证据契约；若有，则进入独立深模块，旧入口只做单向兼容委托。Docker 重建后至少运行新增 surface contract、quick/stage/ci、architecture strict 和 compileall；不要为了降低行数只增加无语义的转发函数。

## M259-B 计划修复与执行重规划迁移后的 workflow evidence 漂移

- **现象**：把计划构建、有限 repair 和执行 replan 从 Runtime 移到 `RuntimePlanningSurface` 后，默认 quick/stage/ci 仍通过，但历史 M150 repair matrix 的文本 fixture 可能因 workflow 模板步骤 ID 演进而显示 `replacement_workflow_invalid`，不能把它误判成 Runtime seam 本身的失败。
- **根因**：规划模块同时接收 Domain 的 workflow blueprint 和模型生成的 TaskPlan；Domain 模板的步骤 ID 是可演进契约，旧 fixture 仍使用早期的 `summary` ID，而当前模板使用 `summary-text`。迁移只改变调用位置，不应偷偷放宽或重写 blueprint 语义。
- **诊断**：先分别检查 `PlanRepairOutcome.status/reason_code`、`plan_quality_before/after` 和 `replan_events.phase`，再与默认 profile 区分；不要只看最终 `FAILED` 或把所有历史 fixture 失败归咎于 Docker/LLM。
- **修复**：M259-B 保持 `PlanRepairEngine` 的严格 workflow 校验，新增 surface contract 只验证 seam 和默认路径；历史 fixture 漂移单独列为兼容矩阵清理项，待全局规划时决定更新模板、fixture 或显式兼容规则。
- **预防**：新 planning seam 必须同时覆盖“候选计划、repair lineage、execution replan merge、workflow quality”四类证据；默认 CI 只保留精简 contract，历史专项失败必须记录独立原因，不能通过删除校验来降绿。

## M259-C 运行生命周期抽取时隐式模块依赖导致终态失败

- **现象**：将 `AgentRuntime.run` 抽到 `runtime_core.run_lifecycle` 后，计划能够生成，结果却在执行完成后变为 `FAILED`；错误不是 GIS 或工具错误，而是 lifecycle 文件缺少原 Runtime 中的 evidence helper import。
- **根因**：物理迁移只复制了方法体，原方法依赖的模块级函数（例如 evidence binding、revalidation 和 failure projection）不会随着 `runtime.` 私有方法替换自动迁移；编译检查只能发现语法问题，正常运行到对应分支才暴露 `NameError`。
- **诊断**：先用最小真实 Runtime 请求走到 `COMPLETED`，再运行 quick/stage/ci；失败时优先查看 `result.error` 和 `failure.phase`，对照迁移方法中所有不带 `runtime.` 的外部符号，不能只看 import 是否成功。
- **修复**：lifecycle 只保留自己的异常/契约 import，并显式导入 evidence binding/revalidation；Runtime 模块级 projection/failure helper 通过运行时延迟模块引用调用，避免初始化阶段循环导入。
- **预防**：方法抽取必须同时做“compileall + 一个成功执行 + 一个澄清/失败路径”三项验证；新 lifecycle seam 的测试应断言终态和 evidence，而不是只断言对象实例存在。

## M259-D Decision resume 抽取时方法名与 owner 绑定漂移

- **现象**：把 `_resume_decision` 迁入新模块后，Runtime 已能创建 seam，但 wrapper 调用的方法名与迁移后的实现不一致，或方法体中的 `self` 已替换为 `runtime` 却没有初始化 owner，导致只在 decision approve 路径运行时失败。
- **根因**：decision resume 同时包含旧私有方法名、状态存储、控制清除和 execution loop；物理抽取时如果只复制方法体而未定义 canonical 方法名与 adapter 注入关系，兼容入口容易“看起来存在、实际不可调用”。
- **诊断**：对新模块做 compileall 只能发现语法问题；还要静态检查 canonical `resume` 方法、Runtime wrapper、owner 初始化三者一致，并构造一个 waiting-for-decision 的最小恢复路径。
- **修复**：canonical 模块使用 `RuntimeDecisionResume.resume`，Runtime 只委托 `_decision_resume.resume(...)`；owner 在 Runtime 初始化时注入，恢复逻辑复用原 Runtime 的 state/control/execution ports。
- **预防**：每个拆分模块明确“canonical 方法名”和“兼容 facade 方法名”，不要让迁移工具自动决定；新增 seam 至少覆盖实例契约、普通成功路径和生命周期恢复路径。

## M259-E Recovery seam 抽取后控制状态不能重复创建

- **现象**：cancel/retry 逻辑从 Runtime 移出后，如果新模块自行创建控制器或状态字典，会出现取消标记只在 facade 可见、retry 清不掉持久标记，或 waiting decision 的拒绝与普通 cancel 产生不同终态。
- **根因**：恢复职责虽然包含状态转换，但状态所有权仍属于 Runtime 注入的 `RunControl`、`DecisionStore` 和 state adapter；把恢复模块误做成新的状态 owner 会破坏跨入口/重启一致性。
- **诊断**：分别验证 active run cancel、waiting-for-decision reject、failed run retry 和 cancel 清除；检查新模块是否只访问 `runtime._control`/`runtime._state_store`/`runtime._decision_store`，没有新建同名状态。
- **修复**：新增 `RuntimeRecoverySurface` 只承载转换与重试循环，所有控制、存储、ToolRegistry、answer 和 observability 通过 owner adapter 复用；Runtime public 方法只做单向委托。
- **预防**：恢复 seam 的契约必须覆盖内存与 SQLite 两种 state adapter 的可见终态，不能只测单进程 happy path；任何新增 recovery state 先登记生命周期契约再实现。

## M259-F Preview 抽取后误写运行状态

- **现象**：把 preview 从 Runtime 主模块抽出时，若直接复用 run lifecycle 的保存逻辑，用户仅点击“预览计划”也会生成运行记录、清理澄清状态或触发工具调用。
- **根因**：preview 与 run 共用请求解析、计划校验和 evidence，但生命周期副作用不同；物理模块拆分若按调用链复制，而不按副作用边界拆分，会把 planning-only 误接到 execution state。
- **诊断**：对同一请求分别执行 preview 和 run，比较工具调用计数、state store、conversation pending、artifact 和 lifecycle 状态；preview 必须只返回 payload，不产生运行状态或 artifact。
- **修复**：新增 `RuntimePreviewSurface`，只依赖 Runtime planning/evidence ports；preview 自己完成 `project_action_lifecycle`，不调用 state save、ToolRegistry dispatch、answer composer 或 memory remember。
- **预防**：preview contract 至少包含“无工具调用、无状态写入、计划 identity 稳定、clarification/rejection 结构一致”四项；不得为了复用代码把 run 的副作用 callback 传给 preview。

## M259-G Plan evidence 迁移后兼容 helper 残留

- **现象**：plan evidence 主函数已经迁移到新模块并能完成正常计划，但澄清/失败路径或 answer fallback 仍引用原 Runtime 中已删除的 helper，造成只在降级分支出现 `NameError`。
- **根因**：evidence 生成函数与 `_planner_source`、`_safe_small_mapping`、`_append_execution_degradation_notice` 等 helper 原本同处一个文件；只迁移主函数会遗漏“被其他 Runtime 生命周期使用的兼容符号”。
- **诊断**：除成功请求外，必须运行能力澄清、计划拒绝、工具失败和 answer fallback；搜索原模块中所有被迁移函数引用的 helper，逐一判断是 canonical import、Runtime wrapper 还是应删除的死代码。
- **修复**：新增 `runtime_core.plan_evidence` canonical projection，Runtime 保留 `_build_plan_evidence` facade，并从 projection 显式导入 answer degradation helper；plan evidence 内部只使用自己的 canonical projection imports。
- **预防**：大函数迁移使用“调用图闭包”清单，不只复制函数体；架构收敛验收必须同时通过成功与降级路径，静态行数下降不能替代行为验证。

## M260-A Service catalog seam 迁移后的运行时选择兼容

- **现象**：将 Service 的 capability、workflow、action、runtime/release evidence 和动态工具逻辑移动到 `CatalogApplication` 后，若直接在新模块捕获 `build_runtime_context_snapshot`，历史测试对 `agent.service.build_runtime_context_snapshot` 的 patch 会失效；异步提交仍可能意外初始化真实 GIS 后端。
- **根因**：异步入口需要在提交阶段获取轻量 runtime context，但自定义 Runtime factory、默认 factory 和 Domain Pack 的快照路径不同；同时旧 Service facade 是既有测试与 HTTP/Async application 的兼容 seam，不能把模块级可替换点悄悄改成导入时固定的函数对象。
- **诊断**：分别验证默认 Domain、显式 Text/Indicators Domain、自定义 Runtime factory 和异步提交；检查提交响应是否在 worker 运行前返回、context 是否绑定 planner/backend/domain，以及 patch Service 入口后是否仍能观测快照调用。不要只验证 `CatalogApplication` 能被 import。
- **修复**：让 `CatalogApplication` 接收 runtime context snapshot builder；Service 传入运行时查找的 lambda，使旧 `agent.service.build_runtime_context_snapshot` patch 继续有效。Runtime selection、workflow normalization 和 dynamic tool registry 全部只在 catalog seam 实现，Service 仅保留单向 wrapper。
- **预防**：应用层拆分时保留“构造时依赖”和“调用时可替换点”的清单；涉及异步、Domain factory 或测试 patch 的 helper 必须注入 callable，不能在新模块中复制一份全局策略。每个 catalog seam 至少跑跨 Domain、动态工具、runtime context、异步提交和自定义 factory 回归。

## M260-B Run query/recovery seam 迁移后的 artifact 与生命周期一致性

- **现象**：把 `get_run`、artifact fallback、evidence index、retry 和 cancel 移出 Service 后，若只验证内存成功路径，SQLite 重启、artifact-only 读取或 action receipt 重放可能丢失 result view、异步观测或 Domain fencing；另一个常见错误是 recovery 模块重新创建控制状态，导致取消和重试在不同入口看到不同终态。
- **根因**：运行查询并不是简单的数据库读取，它还要等待 async job 的最终化、根据持久 runtime context 恢复 planner/backend、重建版本化 result contract，并在没有 SQLite 行时读取 artifact。retry/cancel 又必须复用 ActionApplication 的 receipt 和 Runtime 自己的生命周期状态，不能复制状态 owner。
- **诊断**：按内存成功、SQLite 重启、artifact-only、跨 Domain、显式 retry idempotency、cancel receipt 六类路径检查；比较 `status`、`result.views`、`execution_record`、`evidence_registry`、`async_observability` 和 receipt lineage。不要只断言 `get_run` 返回 200 或最终状态字符串。
- **修复**：新增 `RunRecoveryApplication`，统一负责 Runtime selection inference、快照一致性等待、artifact projection、evidence projection、retry/cancel receipt 以及跨 Domain fencing；所有 state、Runtime、Action receipt 和 async observation 都由构造时注入，不在新模块中创建第二份控制状态。
- **预防**：查询/恢复拆分必须保留“调用图闭包”，把 artifact、result contract、evidence、async 和 Domain identity helper 一起迁移；新 seam 至少运行 SQLite/artifact/receipt/跨 Domain 回归，并保留 Service 的旧方法作为单向 facade，直到所有 transport 迁移完成。

## M260-C Submission seam 验收发现的 Preview 隐式依赖

- **现象**：Service 的 run/preview 提交逻辑移入 `SubmissionApplication` 后，普通 run 可以完成，但 preview 只在真正走到成功计划分支时暴露 `name '_plan_to_dict' is not defined`，进而缺少 `plan_identity` 和 `evidence_binding`；编译检查无法发现这种运行时调用图遗漏。
- **根因**：M259-F 把 preview 实现物理迁移到 `runtime_core/preview.py` 时，原 Runtime 模块中的 `_plan_to_dict`、`_plan_dag` 和 `build_evidence_binding` 依赖没有一并迁入或改为 canonical import。此前只覆盖了对象存在与部分降级路径，遗漏了成功 preview contract。
- **诊断**：对同一个请求同时执行 preview 和 run，至少检查 `status=PLANNED`、`plan_identity`、`plan_evidence.evidence_binding` 和“不调用工具”；若只看 compileall 或 clarification 分支，不能发现成功计划路径的 NameError。
- **修复**：preview seam 显式导入 `runtime_core.projection.plan_to_dict/plan_dag` 与 `evidence_revalidation.build_evidence_binding`，不再依赖 Runtime 私有全局符号；补充 M192/M193 preview identity/evidence gate 回归。
- **预防**：迁移大方法时必须迁移“调用图闭包”，并对成功、澄清、拒绝三条路径分别执行最小 contract；新 Application 不能把编排拆分当成只移动入口方法，所有 artifact、evidence、plan identity 字段都必须在 canonical seam 验证。

## M261-A 数据目录扩展与物理整理后的路径/可用性漂移

- **现象**：新增数据下载后，根目录同时存在原始压缩包、断点分片、已解压瓦片、分析就绪栅格和可直接读取的矢量；如果只修改文件路径而不记录数据状态，Planner 可能选择尚未解压、未裁剪或许可未核验的数据，健康检查也可能对大型水文文件做昂贵探测。
- **根因**：文件存在不等于数据可用于当前请求。数据目录原先只有 `kind/format/role/files`，无法表达覆盖范围、时间范围、CRS、分辨率、处理阶段和“为什么暂时不能选”。物理移动后，旧的 `extracted/...` 引用还会继续指向失效路径。
- **诊断**：先检查 `raw/staged/analysis-ready` 分层和配置相对路径，再用 Docker 的 rasterio/fiona 核验 CRS、范围、尺寸、几何类型和要素数；分别统计 `ready/partial/pending`，不要只看文件是否存在。检查 `get_dataset_health_report(all)` 是否会读取待处理的大文件。
- **修复**：`DatasetCatalog` 增加受控 discovery 元数据和默认 `status=ready` 的 `discover()` 查询；manifest/health 保留 discovery 证据；`pending/partial` 由健康检查返回延迟/不完整状态，不触发昂贵探测。原始压缩包归档到 `raw/archives`，解压数据进入 `staged`，分析就绪层保持独立；所有代码和配置只使用相对路径。
- **预防**：整理数据时先做目标路径和磁盘空间检查，移动前确认源/目标都位于明确的数据根；不删除原始文件，不把断点分片交给 GIS；移动后立即做 JSON 解析、Docker 元数据核验、核心五类健康检查和 quick/stage。新增数据必须先进入目录状态，再决定是否扩展工具或 workflow，不能由文件名触发 Planner 分支。

## M262 架构重构验收时容器镜像与历史 fixture 漂移

- **现象**：宿主机代码已修改，但 `docker exec` 中的架构报告仍显示旧的 `COMPAT_MODULES`；重建后才出现新的 shim/facade/public module 清单。另有一个旧的 M44 规则 fixture 在当前容器配置下返回缺少 `dataset` 的结构化澄清。
- **根因**：生产 compose 只挂载 `data` 和 `outputs`，源码通过 Dockerfile `COPY` 进入镜像；容器不会自动看到工作区代码。历史测试依赖的能力事实也可能随数据目录/环境配置演进，不能把 fixture 失败直接归因于新 seam。
- **诊断**：代码变更后先比较容器内 `scripts/architecture_check.py` 的输出或文件 hash；若与宿主机不同，执行 `docker compose -f docker-compose.prod.yml up -d --build --force-recreate`。对失败运行读取 `status/error/clarification/plan_evidence`，区分“结构化降级”与异常堆栈。
- **修复**：本阶段通过 compose 重建确保镜像包含 canonical source；生命周期、decision、HTTP 和架构 contract 在重建后通过。M44 fixture 作为独立数据/规则兼容项记录，不在架构重构中加入针对单一问句的 dataset 硬编码。
- **预防**：Docker 是项目 Python/GIS 验收环境，不能用本机 Python 替代；每阶段至少执行重建、health、compileall、architecture strict、精简定向回归和 quick/stage。架构清单必须区分简单 shim、兼容 facade 和真实公共模块，真实模块不得用兼容豁免隐藏。

## M263 真实专题数据接入时数据挂载根目录与项目目录不一致

- **现象**：Economic Provider 在容器内能正常注册、计划和执行，但真实查询返回 0 条观测；同一份本地数据在宿主机 `data/economic/` 中存在，容器 `/data/economic/` 却不存在。
- **根因**：Docker Compose 的源码通过镜像 `COPY` 注入，数据通过 volume 注入；`.env.production` 的 `SPATIAL_AGENT_HOST_DATASET_ROOT` 指向宿主机 `D:\dataset\agent`，并不等于项目工作区的 `data/`。被 `.dockerignore` 忽略的 `data/` 也不会进入镜像。
- **诊断**：先读取配置时只显示是否配置，不输出密钥；检查 `docker exec <container> ls -l /data/<domain-data>`，再核对 `.env.production` 的数据根是否存在目标文件。不要只在宿主机运行 Provider。
- **修复**：把不含密钥的规范化数据复制到生产数据根的明确子目录（本例为 `D:\dataset\agent\economic/`），Provider 同时支持 `SPATIAL_AGENT_ECONOMIC_DATA` 显式路径和 `SPATIAL_AGENT_DATASET_ROOT/economic/` 默认发现；重启容器后执行真实 Runtime/HTTP 查询。
- **预防**：每个真实 Domain 都要同时验证“宿主机路径、容器路径、Provider 路径、HTTP 结果”四层；数据目录继续保持 Git ignored，配置文件只登记相对路径和状态，不把外部数据误 COPY 进镜像。

## M263 真实数据验收被持久 SQLite 旧会话污染

- **现象**：跨 Domain 定向测试出现 `session belongs to another domain: default`，同一批测试在隔离 SQLite 后全部通过。
- **根因**：Docker 生产容器挂载了持久 `outputs/spatial-agent.db`；手工 HTTP 验收留下了与测试复用的会话 ID/绑定，测试环境没有自动创建隔离数据库。
- **诊断**：比较失败前后的 `SPATIAL_AGENT_STATE_DB`，检查 session domain binding；先用唯一临时 DB 重跑，不要删除生产 outputs 目录来“修复”测试。
- **修复**：定向/回归测试使用 `SPATIAL_AGENT_STATE_DB=/tmp/<stage>-<run>.db` 等隔离路径；生产容器保留真实 DB，不能为了测试清空用户数据。
- **预防**：测试 profile 必须显式隔离 SQLite、session 和 artifact root；真实 HTTP 验收使用带阶段前缀的 session/idempotency key，并在报告中区分“代码失败”和“环境状态污染”。

## M263 新增 Domain 后旧测试硬编码领域目录

- **现象**：新增 `economic` 和已有 `indicators` Domain 后，跨 Domain 回归中旧测试仍断言目录只有 `gis/text`，导致目录契约和 HTTP `/domains` 契约失败；这不是 Domain 注册或路由逻辑失败。
- **根因**：测试把当时的领域集合当成稳定公共契约，而不是验证“返回完整的已注册集合且不泄露模块实现”。随着 Domain Pack 可扩展，固定列表会在每次新增领域时失真。
- **诊断**：比较 `domain_registry().ids()`、直接 catalog 和 HTTP catalog；若三者一致但测试的旧列表失败，应更新测试契约，不删除合法 Domain。
- **修复**：测试从当前显式 `DomainRegistry` 读取期望 ID，并继续断言顺序、schema 和不包含模块路径；没有放宽未知 Domain 的拒绝校验。
- **预防**：扩展性测试只锁定注册表的公共不变量；只有产品明确规定“允许列表固定”时才写死具体集合。新增 Domain 必须回归直接 catalog、HTTP catalog、URL 路由和 SQLite/artifact 领域过滤。

## M264 指标区域实体解析把连接词或分析尾词吞进区域名

- **现象**：请求“demo_activity_index 区域甲和区域乙的趋势”被解析成 `区域甲` 与 `区域乙的趋势`，或先前解析成 `区域甲` 与 `和区`，Provider 因找不到第二个区域而失败。
- **根因**：区域正则只按字符结尾匹配 `市/区/县`，没有先处理中文连接词，也没有识别实体后面的“趋势/比较/分析”等任务表达；Domain facts 与 Rule Planner 还各自维护一份解析器。
- **诊断**：在运行前检查 `request_facts.entities.regions` 和计划中的 `regions`，不要只看 Provider 的“无数据”错误；对连接词、实体尾部任务词和连续行政区名称分别做最小复现。
- **修复**：先移除明确的连接词与句尾任务词，再使用非贪婪区域匹配；同步修正 Domain facts 与 Rule Planner，保留真实区域名称，不把解析逻辑放进公共 Runtime 或 Provider。
- **预防**：领域新增自然语言表达时，必须同时验证 facts、Rule Planner、LLM Planner context 和 ToolRegistry 参数；后续可将已被两个 Domain 证明的实体解析抽为公共请求理解模块，但不能在指标核心中加入领域词表。

## M265 阶段文档中的测试模块名与实际文件漂移

- **现象**：M265 Spec 初稿把 M249 回归写成 `tests.test_m249_open_planner_context`，但仓库实际文件为 `tests/test_m249_open_planner.py`；照抄命令会在 Docker 中得到 `ModuleNotFoundError`，容易把文档错误误判为代码回归。
- **根因**：阶段文档按能力描述命名测试，而 Python unittest 入口按实际文件/模块命名；重构或测试精简后，文档没有与 `tests/` 当前目录核对。
- **诊断**：执行阶段命令前先用 `rg --files tests | rg 'm249|m265'` 核对文件，再将路径转换为模块名；阶段回归报告必须记录实际执行的命令和数量。
- **修复**：将命令改为 `tests.test_m249_open_planner`，并在 M265 收口证据中记录 14/14、stage、quick、compileall 和 architecture strict 结果。
- **预防**：Spec/Plan 中的测试命令只引用已存在的模块；测试重命名后同步更新文档，并在 Docker 中先运行定向命令，再运行 profile，避免只依赖静态检查。

## M266 声明式 catalog 校验不能替代 ToolRegistry 执行校验

- **现象**：把 Domain 的 capability/workflow 声明集中到公共 builder 后，容易误以为 catalog 中的工具白名单就是执行授权；如果只校验能力声明而跳过 ToolRegistry，模型可能选择未注册工具或传入不符合 schema 的参数。
- **根因**：catalog 是 Planner-facing 的能力发现投影，ToolRegistry 才拥有最终注册、schema、参数、权限和 dispatch 约束；两者用途相近但生命周期不同。
- **诊断**：分别检查 Domain catalog 的 known tools、Planner context 的 tool schemas，以及运行时 `ToolRegistry` 的 definition/dispatch；不能只断言 capability catalog 返回了工具名。
- **修复**：M266 builder 只做声明间的 bounded cross-reference 校验，并保留已有 ToolRegistry；没有把工具执行、权限或参数校验移入公共 catalog 工厂。
- **预防**：新增专题先写 DomainCatalogSpec，再通过 ToolRegistry 注册工具并运行 Planner→Runtime→dispatch contract；catalog 只说明可发现能力，执行前仍必须重新校验工具和数据事实。

## M266 新增公共契约未登记到架构守卫清单

- **现象**：`agent/domain_catalog.py` 已成为真实公共声明/校验模块，但 `architecture_check.py` 的 `PUBLIC_MODULES` 未同步登记；架构报告仍可能通过，却无法反映该模块的分类。
- **根因**：实现文件、架构守卫和阶段文档是三个独立清单，新增 canonical seam 时只更新了代码和测试。
- **诊断**：每次新增 `agent/` 下的公共 seam，都要比较模块导出职责、架构清单和报告中的 `public_modules`，不能只看 errors/warnings 是否为空。
- **修复**：将 `agent/domain_catalog.py` 加入 `PUBLIC_MODULES`，并重新运行 architecture strict。
- **预防**：Spec/Plan 的收口任务同时包含“新增公共模块登记”和报告抽查；公共模块不得落入 `COMPAT_SHIMS` 或 `COMPAT_FACADES`。

## M267 公共 catalog 把派生数据集误判为未知物理数据

- **现象**：GIS `legacy_road_slope` 能力声明了 `slope`，但物理 `dataset_tool_capabilities` 只有 `admin_areas/dem/land_use/roads/water`；直接用 M266 校验器迁移时被拒绝为 unknown dataset。
- **根因**：能力依赖集合同时包含物理数据集和由前序栅格/空间步骤产生的虚拟数据集，原声明没有表达两者差异；不能为了通过校验把派生数据伪造为 DatasetCatalog ready 条目。
- **诊断**：对每个 capability dataset 先与物理 DatasetCatalog/Provider 映射求差集，再检查是否有前序工具或 Domain preflight 产生该依赖；同时比较 dataset groups、health/readiness 和 Planner context，不能只看字符串是否存在。
- **修复**：M267 增加领域中立的 `derived_datasets` 声明；公共 builder 允许 capability 引用派生依赖，并在 Planner context 显示 `derived_datasets`，但不生成 dataset evidence 或 ready 状态。
- **预防**：新增专题的 catalog Spec 必须显式区分 physical/derived/optional 数据；派生数据仍需由 Runtime/ToolRegistry/Domain preflight 校验来源和对齐，公共 catalog 不得放宽执行门禁。

## M268 文件型矢量扩展不能依赖固定 dataset allowlist

- **现象**：真实 `earthquakes_wuhan` 已在 DatasetCatalog 中登记，但旧 `GeoPackageBackend` 只构造 `roads/water` 两个条目；即使 `range_query` 本身支持任意字段条件，新增 GeoJSON 仍会被后端当成未知数据集。
- **根因**：工具能力、数据发现和文件格式读取被混在一个按 dataset 名称分支中；另外结果标签只读取 `name`，没有 `name` 的事件数据会在 `.tolist()` 处出错。
- **诊断**：先比较 `DatasetCatalog.discover(kind="vector")`、后端 `supports()`、ToolRegistry 的 schema 和实际文件格式；再分别验证有 `name`、只有 `place`、只有 `id` 的矢量查询。不要只验证固定 roads/water 回归。
- **修复**：M268 保留旧类名作为兼容 seam，但按 Catalog 发现所有 ready vector 条目；GeoPackage 使用 dataset layer，GeoJSON/其他文件按路径读取；结果标签按 `name → place → id` 有界回退，roads/water 的历史分类逻辑保持不变。
- **预防**：新增同类型专题优先登记 DatasetEntry、格式和来源，再复用通用 schema/query；只有新增业务语义时才在 Domain Catalog 声明 capability，不在 Runtime 或 Adapter 中加入专题名称判断。

## M268 Docker 默认挂载与真实数据挂载根不一致

- **现象**：容器环境变量中的 `SPATIAL_AGENT_HOST_DATASET_ROOT` 显示为 `D:/dataset/agent`，但 `docker inspect` 实际显示 `/data` 绑定到项目 `D:\Project\job\ai-agent\data`，容器内看不到 `downloads/wuhan-gis`。
- **根因**：Compose 的 volume 插值发生在 Compose 解析阶段，`env_file` 中的变量只注入容器，不参与同一 Compose 文件的宿主路径插值；因此 Compose 使用了默认 `./data`。
- **诊断**：同时检查 `docker inspect <container> .Mounts`、容器内 `/data` 内容和宿主机数据文件；只打印配置路径/存在性，不输出 API key 或完整私密环境变量。
- **修复**：默认生产容器继续使用项目 `data/`，真实验收使用一次性 `docker compose run --no-deps -v D:/dataset/agent:/data:ro -e SPATIAL_AGENT_DATASET_CONFIG=/app/config/datasets.container.earthquakes.example.json ...` 显式挂载；真实原始数据不进入镜像或 Git。
- **预防**：每条真实 GIS 验收都记录 host path、container path、DatasetCatalog path 和实际结果四层证据；不要仅凭容器环境变量判断 volume 已切换，也不要为测试清空持久 outputs/SQLite。

## M268 历史回答文案断言阻塞精简回归

- **现象**：旧 M50/M51/M62 测试硬编码“OpenStreetMap”“数据预检”“道路摘要”等回答措辞；回答生成边界演进后，实际结构化事实仍正确但回归失败。
- **根因**：测试把用户可见自然语言的某个版本当成稳定接口，未区分 Result/Trace/Evidence 契约与可变的回答表达。
- **诊断**：失败时先比较结果类型、步骤工具、核心数值和状态，再判断是否只是文案漂移；不要为恢复旧短语给 Composer 增加兼容分支。
- **修复**：将断言改为道路/水体、阈值、数据状态等稳定事实，保留必要的用户可读性检查；M268 Docker 历史 GIS/回答契约 47/47 通过。
- **预防**：默认测试优先验证结构化 Result/View/Evidence、步骤和关键数值；仅在产品明确要求时锁定完整回答句式，模型回答测试使用 schema/语义关键事实而不是整句匹配。

## M269 Agent-grade 架构与 query-engine 体验脱节

- **现象**：Runtime 已具备能力发现、Planner、DAG、生命周期、恢复和 Evidence，但用户日常看到的仍主要是“提问 → 查询 → 返回”；复杂请求经常由 Rule Planner 命中固定模板，前端的计划和执行轨迹又默认折叠，Agent 的自主规划过程没有传导到体验。
- **根因**：默认入口仍有 `planner=rule`、`backend=memory` 的兼容默认值；数据发现只覆盖已登记且 ready 的目录；Rule Planner 使用领域内固定 builder；LLM Planner 虽可组合已注册工具，但不是所有入口的默认路径；前端把过程证据全部放进高级详情。
- **诊断**：分别记录入口实际的 planner/backend、`planner_source`、能力发现状态、计划步骤数、工具 DAG、数据目录投影和前端可见阶段；不能只看最终 `COMPLETED`，也不能用前端没有展示 trace 推断 Runtime 没有执行轨迹。
- **修复方向**：保持 Runtime/ToolRegistry 生命周期不变，优先统一可配置的真实 LLM + 本地数据体验；让 Rule Planner 明确成为离线/确定性/降级路径；在对话区增加不暴露思维链的结构化阶段里程碑、计划摘要、数据选择和下一步动作；继续扩展通用工具组合与受控数据探索。
- **预防**：每个跨领域阶段同时验收 Agent Runtime 契约和用户体验契约；真实 LLM 验收需证明能力发现、计划生成、多步执行和证据入口可见，前端不得按工具名或领域写专用分支，也不得展示模型内部思维链。

## M269 通用记录分析 Adapter 的调用图遗漏与周期语义漂移

- **现象**：核心 `RecordAnalysisEngine` 和 Protocol 已存在，纯核心单测通过，但真实文件矢量通过 ToolRegistry 调用 `record_analysis` 时先出现管理区加载参数错误，随后暴露 `GeoPackageBackend` 缺少实现；指标 Provider 对季度/半年期间使用字符串比较也可能筛选错误。
- **根因**：迁移通用能力时只接了接口、核心和部分后端，没有按 `ToolRegistry → SpatialToolAdapter → Hybrid/GeoJSON/GeoPackage → shared engine` 验证完整调用图；同时把领域特有的期间排序误当成通用字符串比较，丢失了 Indicator Domain 的 `_period_key` 语义。
- **诊断**：先在 Docker 中执行真实 Adapter contract，而不是只执行 compileall/核心单测；检查 `record_analysis_result.status/result_type/metrics`。指标问题要用 `Q2/Q10` 或 `H1/H2` 这类最小周期 fixture 对比 Domain period key 和通用字段过滤。
- **修复**：GeoJSON 管理区使用无参数 `_load()` 并提供明确 provenance；GeoPackage 实现属性投影后调用共享核心；Hybrid 对真实管理区和文件矢量分别路由。Indicator 核心继续委托通用字段筛选，但 start/end 期间范围在 Domain 内用 `_period_key` 过滤。
- **预防**：新增通用工具时必须覆盖 Protocol、每个真实 Adapter、Hybrid 路由、ToolRegistry schema、Result/View 和一次真实数据验收；领域时间/空间语义只能留在 Domain Adapter，不能为了复用塞入公共记录核心。文档中的测试模块名与 Docker 实际命令要同步核对。

## M270 中转模型 live 验收无输出并长时间挂起

- **现象**：Docker 使用已配置的中转地址 `opencode.ai/zen/go/v1`、`deepseek-v4-flash`，显式开启 live GIS 只跑一条真实模型概况请求；约 90 秒没有任何有界摘要或错误，进程只能人工终止。此前宿主直连还出现过 WinError 10013，因此不能把这次现象归类为 GIS 工具执行失败。
- **根因判断**：请求可能卡在中转网络连接、代理转发或 provider 超时边界；当前 live baseline 在最终报告前没有逐阶段心跳输出，导致“正在规划”与“请求已挂起”对用户不可区分。现有默认离线/规则路径不受影响。
- **诊断**：只记录 provider、model、wire api、阶段、耗时、是否产生 TaskPlan/工具步骤和结构化错误码；不输出 API key、请求头、prompt 或模型原文。用 `SPATIAL_AGENT_LIVE_OPENAI=1`、`SPATIAL_AGENT_LIVE_GIS=1` 在 Docker 单独跑一条请求，超过有界时间后停止；再用 fake/Rule Planner 验证 Runtime 和 GIS。
- **处理建议**：下一阶段为 live acceptance harness 增加连接/规划/执行阶段心跳、总 deadline 和 provider failure receipt；中转不可用时明确返回可恢复 provider 状态，不修改 ToolRegistry、GIS 算法或 Runtime 主链路来绕过网络问题。默认 CI 继续不调用真实模型。
- **预防**：真实模型验收必须 async-first、单次提交、有界轮询和分阶段超时；每个外部 provider 先做最小 health/capability probe，再决定是否进入昂贵的复杂请求。中转路径与直连路径分别记录，不把一条路径的失败外推为模型或 GIS 全部不可用。

## M270 live harness 超时边界与安全进度输出

- **现象**：原 live baseline 只有最终报告；provider 在规划阶段挂起时，命令行没有任何阶段性信息，用户无法判断仍在工作、网络等待还是已经失效。
- **根因**：验收脚本直接同步等待 Runtime/provider 调用，缺少独立的 harness deadline 和进度回调边界；业务 Runtime 的正常执行 deadline 不能可靠约束第三方网络线程。
- **修复**：`evaluation/live_baseline.py` 为每个 case 增加有界 daemon worker、总 deadline、`started/heartbeat/completed/timeout` 事件和脱敏 timeout receipt；`scripts/live_baseline.py` 增加 `--deadline-seconds` 与 `--heartbeat-seconds`，只把白名单事件写入 stderr。超时不自动重复提交请求，也不伪装成成功降级结果。
- **安全边界**：事件只允许 `event/case_id/phase/status/elapsed_ms`；receipt 不包含 prompt、请求头、API key、模型原文、完整异常或宿主路径。后台第三方线程无法被强制终止，因此只保证 harness 主线程有界返回，不宣称取消 provider 网络调用。
- **验证**：Docker M270 定向 **3/3**（立即成功、阻塞超时、参数校验），M269/M268/M264 相邻回归 **14/14**，compileall、architecture strict、quick/stage 通过。真实中转 provider 仍需显式 probe，不能用 fake harness 结果替代真实模型验收。
- **预防**：新增 live provider 时先用单 case、短 deadline 的 probe，确认 provider 可达且能返回结构化计划后再进入 GIS 多步验收；默认 CI/quick/stage 继续离线，不把网络抖动变成全局代码失败。

## M271 Provider 可达不等于 Agent 多步能力可用

- **现象**：中转 provider 的最小结构化 JSON 请求可以在 15 秒内成功返回，但这只能说明网络、认证、wire API 和 JSON 解码链路可用；不能据此断言 LLM Planner 能根据能力目录生成合法 TaskPlan，更不能断言 GIS 工具 DAG 能执行。
- **根因**：provider 接入、Planner 计划理解、ToolRegistry schema 校验和 Domain 数据执行属于不同 seam；把一次模型健康请求与完整业务请求混为一个验收，会导致失败归因和阶段结论失真。
- **修复**：新增 `evaluation/live_provider_probe.py` 与显式 `scripts/live_provider_probe.py`。Probe 使用已有 `OpenAIPlannerClient`，单次请求、`max_retries=0`、有界 timeout，返回固定 `live-provider-probe` receipt；不进入 Runtime，不触发 GIS，不自动切换中转/直连。
- **验证**：Docker M271/M270 定向 **7/7**，M269/M268/M264 相邻回归 **14/14**，compileall、architecture strict、quick/stage 通过；真实中转 probe 返回 READY、Chat Completions、1 次请求、0 次重试。receipt 未保存 prompt、key、模型原文或路径。
- **预防**：真实验收必须按“provider probe → Planner/能力选择 → TaskPlan/工具 DAG → 实际数据执行 → 结果/evidence/前端”分层；只有下一层成功后才能进入更昂贵的复杂请求。每层失败使用独立错误分类，不把 provider READY 当作 Agent 完成度。

## M272 真实 LLM local timeout 与 GIS 失败的归因

- **现象**：同一开放式“分析洪山区空间概况”请求，provider probe READY；真实 LLM + memory 完成，Rule Planner + local GIS 8 步完成；真实 LLM + local 在 provider timeout=20 秒时失败且 0 工具步骤，放宽到 provider 45 秒、harness 90 秒后完成，约 36 秒。
- **诊断**：Planner 脱敏投影的 local/memory prompt 大小几乎相同（约 14 KB，schema 651 B）；失败发生在 Planner provider call，未进入 GIS 工具。因此不能把短 timeout 失败归类为 Rasterio/GDAL、数据对齐或 Runtime 执行错误。
- **修复**：不修改业务链路；修正 live baseline 事件投影：运行时自身返回 `error_class=timeout` 时仍输出 `completed + status=FAILED`，只有 harness 产生 `deadline_exceeded=true` 的 timeout receipt 才输出 `event=timeout`。新增最小契约测试覆盖两种 timeout。
- **验证**：Docker M270/M271 harness **8/8**；真实 LLM + memory、Rule Planner + local GIS、真实 LLM + local GIS 均完成；中转请求使用 1 次调用、0 次重试。结论是中转 latency 有波动但当前配置可完成，不是 GIS/Runtime 缺陷。
- **预防**：真实模型验收同时记录 provider timeout、harness deadline、工具步骤数和 backend；先用短 probe/对照定位，再调大 provider deadline。不要通过增加 Runtime 重试或修改 GIS 算法掩盖 provider 波动。

## M273 live harness 不能把 Domain 选择写成 GIS 专用分支

- **现象**：live baseline 原本按一套默认 `build_runtime(planner, backend)` 运行，新增 Economic 真实模型 case 时，复用同一 harness 的能力不足；如果直接在脚本中判断 Economic，就会把验收逻辑重新绑定到某个领域。
- **根因**：live case 的 Domain 身份没有成为 composition root 的显式输入；同时 local backend 的 GIS gate 被误当成所有 local Domain 都必须满足的前置条件。harness 的 case contract、Runtime factory 和环境门控三者没有对齐。
- **诊断**：检查 case 的 `domain_id`、runtime factory 实际调用参数、按 Domain 缓存键和 `_case_requires_gis()`；再用 fake factory 验证旧两参数调用与新 `domain_id` 转发，不要只跑真实模型。
- **修复**：M273 为 case 增加受限 `domain_id`，只在 composition root 选择已注册 Domain；按 `backend + domain_id` 缓存 Runtime，旧 factory 保持兼容；Economic case 不要求 `SPATIAL_AGENT_LIVE_GIS=1`，GIS/legacy case 仍要求显式 GIS gate。Domain ID 只作为有界 evidence，不把 Domain 判断下沉到 Runtime、Planner 或前端。
- **验证**：Docker M273 **2/2**；相关 M270/M271/M263/M79/M269/M268/M264 回归 **53/53**；compileall、architecture strict、quick/stage 通过；真实 Economic LLM + Docker 数据 `live-economic-gdp-trend` 通过，1 次请求、0 重试、约 20.3 秒、4876 tokens。
- **预防**：以后新增 Domain 的 live 验收先扩展 case contract 和 composition root，再复用统一 Result/Evidence 评估；真实跨领域单次混合请求另行设计 Composite Domain/Workflow Spec，不在 harness 中偷偷拼接两个 Runtime。默认 CI、quick、stage 继续离线。

## M274 中转不接受 Domain Selector 的复杂严格 schema

- **现象**：Planner 使用同一 OpenAI-compatible 中转和 `json_object` 可以工作，但 Domain Selector 传递嵌套候选/nullable 字段的 strict `json_schema` 时收到 HTTP 400；直接把它归为 Runtime 或 Domain 数据错误会误导排查。
- **根因**：中转对 Chat Completions 的 JSON Schema 子集支持不一致；Selector 本身已经有本地身份校验，却把 provider 端 schema 支持误当成必需前置。
- **诊断**：只看脱敏 provider metrics：`response_status=400`、`error_type=http_error`、无工具步骤；对比同一 client 的 Planner `json_object` 请求。禁止读取/打印响应体、API key、prompt 或完整模型原文。
- **修复**：M274 让 `OpenAIDomainSelectorAdapter` 传入 identity schema 供应用侧契约使用，但调用 `complete_json(..., schema_name=None)`，让兼容客户端使用 JSON object wire format；`ModelDomainSelector` 继续校验状态、候选数量、注册 Domain/capability 和请求指纹，未知输出仍 fallback。
- **补充修复**：Economic Domain 在自身 catalog 中声明规范指标 ID 和别名。对于 `gdp_total/GDP + 明确经济语义`，catalog fallback 选择 Economic；语义不足时返回 ambiguity，不强行选择通用 Indicators。
- **验证**：Docker M274/M273/M270/M271/M263/M269 **24/24**，compileall、architecture strict、quick/stage 通过。真实 selector 单独调用在 90 秒内 provider 返回成功但模型 identity 不合法，安全 fallback；完整全新 session auto case 遇 transient provider 后仍由 catalog 选择 Economic，`economic_indicator_query` 与 `economic_source_evidence` 两步完成，结果为 `economic_timeseries_result`。
- **预防**：provider schema 兼容性必须通过最小 probe 和 live metrics 分层验证；身份安全不能依赖第三方 schema 强制，而要在本地做 allowlist 校验。Selector fallback 的成功只能证明降级链路，不等同于模型 selector 成功；默认 CI、quick、stage 保持离线。

## M275 Composite 契约不能等同于跨 Domain 执行能力

- **现象**：项目已有 `composite` data profile 和 Domain 内部组合 workflow，但它们不能证明一次用户请求已经跨 GIS/Economic 两个独立 Domain 执行；若只把多个结果拼成列表，可能丢失组件失败、Domain 身份、View 冲突和证据血缘。
- **根因**：`DomainRuntimeHost` 当前按一次请求选择一个 Domain，公共 Result Envelope 虽支持 composite 类型，却没有跨 Domain coordinator 的组件 DAG、结果聚合和统一 evidence 投影边界。
- **诊断**：先区分“单 Domain 内部 workflow composition”“结果 data profile=composite”和“真正跨 Domain coordinator”三种状态；验收必须检查组件 Domain/状态/依赖、profile 并集、子 View 引用、artifact/evidence 和部分失败，而不是只看最终 `COMPLETED`。
- **修复**：M275 新增领域中立 `agent/composite_contract.py`，以 `spatial-agent.composite-request.v1`、`composite-result.v1`、`composite-evidence.v1` 规范化有界组件 DAG，聚合 `vector/raster/metrics/timeseries/document_evidence`，对缺失/失败/阻塞组件保留结构化状态，使用组件前缀隔离子 View；`nested_schema` 和 Evidence Registry 复用同一边界。当前只完成契约接缝，未把 coordinator 或 HTTP/async 生命周期伪装成已完成。
- **验证**：Docker M275 契约 **4/4**，compileall、architecture strict、quick/stage 通过；测试覆盖正常混合、依赖环、必需组件失败和缺失组件阻塞。未保存模型原文、密钥、真实原始数据或宿主路径。
- **预防**：后续跨 Domain coordinator 必须先通过 Host allowlist 再执行每个组件，并将同步、异步、artifact、SQLite/restart 和前端统一到同一 Composite Result/Evidence；不得在 live harness 或某个 Domain 内偷偷拼接两个 Runtime，也不得把 Composite schema 当作跨域端到端验收证据。

## M276 Coordinator 第一条执行切片不能代替完整跨域生命周期

- **现象**：Composite request/result 契约已经可以描述多个组件，但如果直接在 HTTP 或 live harness 中临时循环调用多个 Service，会绕过统一 session、async、artifact、SQLite/restart 和前端结果边界。
- **根因**：跨 Domain 执行需要一个明确的 application seam；`DomainRuntimeHost` 只负责 allowlist 和 Service ownership，不能由 transport 自己拼接执行流程。
- **诊断**：检查未知 Domain 是否在任何 Service 调用前拒绝；检查依赖失败是否阻止下游而不影响独立组件；检查子 Service 异常是否保留为组件 receipt；最后检查聚合结果是否仍能通过 M275 nested schema。
- **修复**：M276 新增 `agent/application/composite.py` 的 `CompositeApplication`。它只调用 Host `select/service` 和子 Service `run`，按声明顺序串行执行；依赖 gate 产生 `blocked`，组件异常产生有界 `failed` receipt，最后复用 M275 `build_composite_result_contract`。未知/禁用 Domain 作为请求级 `CompositeCoordinatorError` 拒绝。
- **验证**：Docker M275+M276 定向 **9/9**，compileall、architecture strict、quick/stage 通过；真实 Host allowlist、正常顺序、依赖阻断、独立组件继续执行和敏感异常不回传均有契约覆盖。
- **预防**：后续 HTTP/async/artifact/SQLite/restart 只能调用同一 Coordinator seam；不要在 Domain Pack、live harness 或 transport 层复制组件循环。M276 不宣称已经具备 LLM 自动生成跨域计划或完整跨入口恢复。

## M277 FastAPI Composition Root 变量名漂移导致容器启动失败

- **现象**：新增 Composite HTTP 注入后，Docker stdlib 测试通过，但生产 FastAPI 容器启动失败，`/health/ready` 连接被提前关闭；日志只显示模块导入阶段的 `NameError`。
- **根因**：两个入口的 Host 变量命名不同：`serve_api.py` 使用 `domain_host`，`production_api.py` 使用 `host`。复制注入代码时误将 stdlib 变量名带入 FastAPI Composition Root。
- **诊断**：新增入口级依赖后必须重建 Docker 并检查容器日志、`/health/ready` 和实际 import；不能只运行应用层单测。
- **修复**：生产入口改用其已初始化的 `host` 创建 `CompositeApplication`；随后 Docker 重建、生产容器恢复并返回 HTTP 200。
- **验证**：M277 应用/Composite/stdlib HTTP 定向 **16/16**，compileall、architecture strict、CI/stage 通过；真实 Docker `/composite-runs` 的 GIS + Economic 请求返回 `COMPLETED`，失败组件请求返回结构化 `FAILED`。
- **预防**：两个 transport 共享 semantic Application，但 Composition Root 注入时必须以各自实际变量为准；以后每次 transport 改动都至少执行 Docker import/health 验收，并记录启动失败而非只保留最终绿灯。

## 上下文恢复默认加载过多历史文件

- **现象**：新对话或上下文压缩后，如果同时读取完整恢复卡、任务档案、问题日志、milestones、归档和全量测试，当前阶段、最近任务和待修改文件会被历史内容淹没，恢复成本随阶段数增长。
- **根因**：历史总结与当前工作状态没有分离；恢复脚本虽然只调用一个入口，但入口指向的是不断追加的长文档，无法表达“当前只需要读哪些文件”。
- **修复**：新增 `docs/agent-work-state.md` 作为短快照，记录当前 goal 摘要、阶段 Spec/Plan、最近进行中的任务、明确待修改文件、验证命令、阻塞和下一步；`scripts/resume_context.ps1` 默认只读取该文件。`-Topic` 默认只在快照和 `tasks/` 中做有界检索，只有显式 `-IncludeHistory` 才读取历史文档。
- **预防**：每个子任务完成或暂停时立即更新快照；阶段完成后再同步历史恢复卡和 milestones。恢复代理不得默认打开完整问题日志、milestones、归档、全量测试或模型响应。

## M278 Docker 镜像未重建导致新增测试不可见

- **现象**：宿主工作树已经加入 M278 的 HTTP/重启测试，但首次 Docker 定向命令只发现旧的 4 个测试，新增测试没有执行。
- **根因**：生产 compose 的测试容器使用已构建镜像；仅修改工作树不会自动把源码同步到旧镜像，测试结果因此不能代表当前工作树。
- **诊断**：比较 Docker 输出中的测试数量与当前文件中的测试方法；发现数量异常时先检查镜像构建时间/compose 是否挂载源码，不要把“未发现测试”误判为测试通过。
- **修复**：先执行 `docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent`，再运行定向测试；阶段验收前用新镜像 `up -d --force-recreate` 并检查 `/health/ready` 和实际 HTTP 请求。
- **预防**：任何新增或修改 Python 测试后，Docker 验收必须显式重建镜像；记录测试总数、compileall、architecture strict、CI/stage 和生产 health，避免只复用旧容器绿灯。

## M278 Composite 跨入口恢复必须复用同一生命周期

- **现象**：Composite 同步、异步、detail、observability、evidence 和重启接管分别位于多个入口；若 transport 自己循环组件或重建状态机，会出现结果、幂等和证据不一致。
- **根因**：Composite Coordinator 的组件编排与 AsyncApplication 的 run lifecycle 属于不同边界；HTTP 入口只负责 URL/资源解析，不能成为第二个生命周期 owner。
- **诊断**：只检查 `HTTPApplication` 的 semantic command 调用、FastAPI/stdlib 路由结果是否相同，以及 SQLite orphan job 的 `owner_pid/recovery_count/组件执行次数`；不要以单个同步成功响应代替恢复验收。
- **修复**：新增 `CompositeRunApplication`，注入既有 `AsyncApplication`，使用独立 `composite` scope 保存 canonical Result；FastAPI/stdlib 都调用同一 HTTPApplication。新增 artifact-only、幂等和失效 owner 重启接管测试。
- **验证**：Docker M278 生命周期/HTTP 与 M277/M256/M275/M276 联合 **23/23**；compileall、architecture strict、CI/stage、生产 `/health/ready` 通过；真实 Docker async/detail/observability/evidence 返回 `COMPLETED`、`composite_result`、artifact/evidence 可用。
- **预防**：后续 LLM Composite Planner、前端动态 View 和跨领域 live 验收都必须消费 M278 的 request/result/evidence/lifecycle 边界，不在 transport、Domain Pack 或前端复制组件循环。

## M279 中转模型可达但 Composite Planner 输出契约不兼容

- **现象**：真实中转 `/composite-plans` 请求返回 HTTP 200，但 Planner 结果为结构化 `REJECTED/plan_outcome_invalid`，没有组件和 `run_id`；规则模式则按设计返回 `NEEDS_CLARIFICATION`。
- **根因**：provider 可达、JSON 请求成功，不等于模型遵守 Composite Planner 的 `outcome`/组件 schema。不能把 provider READY 或 HTTP 200 当作合法 DAG 生成成功。
- **诊断**：只检查 `status`、`planner_source`、`error_code`、组件数量和是否创建 run；不读取或输出 prompt、响应原文、密钥、请求头或私有路径。用 Rule/fake/LLM 三条 seam 分层对照。
- **修复**：M279 在本地对模型输出执行 schema/allowlist/Composite request normalize；非法 outcome 在执行前拒绝，保留有限错误码；HTTP 仍返回安全结构化结果，不创建 Composite execution run。
- **验证**：真实中转 planning probe HTTP 200、`REJECTED/plan_outcome_invalid`、无 run；Docker M279/M278/M277/M256/M275/M276 **33/33**，CI/stage、compileall、architecture strict 和生产 health 通过。
- **预防**：真实验收继续按 provider probe → Planner contract → canonical DAG → execution 分层；后续只在 Planner/provider adapter 层优化 schema 兼容，不在 Runtime、ToolRegistry、GIS 算法或 transport 中绕过校验。

## M280 Git push 短暂凭据失败后重试恢复

- **现象**：M280 规划本地提交成功，但首次 `git push` 返回 `SEC_E_NO_CREDENTIALS`；代码和提交本身没有错误。
- **根因**：宿主 Git Credential Manager/Schannel 短暂没有可用凭据，属于远端认证接缝，不应修改项目代码或提交密钥来绕过。
- **诊断**：先确认本地 commit/hash 和工作树，再原样重试 `git push`；不要打印 remote token、凭据、环境变量或修改仓库认证配置。
- **修复**：第二次 `git push` 成功，`2580b84` 已到 `origin/main`。
- **预防**：阶段交付同时记录本地 commit 与远端 push；首次凭据/网络错误只安全重试，连续失败时保留本地提交并等待外部认证恢复。

## M280 中转 Composite Planner 输出不稳定，不能盲目放宽 schema

- **现象**：显式 Docker planning probe 已到达中转，但一次返回 `REJECTED/plan_response_field_invalid`，另一次返回非 JSON provider response；两次均为 0 个组件、无 `run_id`，真实 GIS/Economic 执行未被错误触发。
- **根因**：provider 可达、基础 JSON probe 成功，不代表模型在复杂 Composite 请求中稳定遵守 `outcome/goal/components` 和组件字段契约；中转可能出现旧式 wrapper、字段漂移或非 JSON 输出。
- **诊断**：只保留 `status`、`error_code`、组件数、fingerprint、schema 状态和耗时；不得读取/打印/提交 prompt、模型原文、请求头、密钥、响应体或私有路径。用 fake/replay 与真实 planning probe 分层对照。
- **修复**：M280 新增独立有界 normalizer，允许文档化 `plan/status/objective/steps` 等映射、有限默认 outcome 和组件常见命名；未知字段/别名冲突 fail closed。Planning Application 输出脱敏 compatibility/evidence；真实失败保留结构化 receipt。
- **验证**：Docker M280/M279 Planner 回归 **15/15**；M278 lifecycle/HTTP + M280 acceptance **12/12**；真实 GIS + Economic sync/async/evidence/restart 全部通过。未修改 Runtime、ToolRegistry、GIS 算法或 Composite schema 版本。
- **预防**：把 provider readiness、Planner contract、canonical DAG、真实执行分成独立门禁；兼容面必须有明确别名和离线回放用例，不能为了让一次 live 请求通过而接受任意字段或绕过 capability allowlist。

## M281 浏览器 overview smoke 的默认问句进入澄清

- **现象**：生产 Docker/浏览器环境运行旧的 overview smoke 默认问句时，页面最终显示“等待澄清”，没有生成结果面板；地图 renderer smoke 和 Composite Projection smoke 正常通过。
- **根因**：该问句没有提供当前规则规划器要求的完整范围/能力信息，系统按统一澄清契约结束，不应把澄清状态当作前端卡死或成功结果。第一次并行运行多个 browser smoke 时还会因共用一个 CDP 页面互相导航，造成假失败。
- **诊断**：浏览器 smoke 必须串行执行；分别检查 `status`、交互/澄清证据和结果面板。若状态为澄清，先换成明确的验收请求或直接注入最小 Projection fixture 验证 renderer，不要修改前端去绕过澄清。
- **修复**：本阶段新增 Composite Projection browser smoke，验证 `projectionToPanels()`、答案摘要、generic/visual 两个 surface 和地图要素；保留默认 overview smoke 的澄清结果作为输入契约提示。
- **验证**：Docker M281/M278/M279 **19/19**；Composite Projection browser smoke、地图 browser smoke、JS syntax、compileall、architecture strict 通过。
- **预防**：browser smoke 共享 CDP 页面时采用串行队列；测试问句与当前 Spec 的必填事实保持同步，并区分澄清、失败、加载和渲染错误四种状态。
## 上下文恢复仍需要独立的任务进度账本

- **现象**：已有工作快照和 `tasks/task-state.md` 后，恢复入口仍容易把当前状态、最近完成任务和历史阶段记录混在一起；随着阶段增加，恢复时读取内容变长，当前要改文件和下一步不够突出。
- **根因**：`tasks/task-state.md` 同时承担详细状态与恢复摘要，`tasks/todo.md` 又只保存阶段清单，没有一个只面向“进行中/最近完成子任务”的短账本。
- **诊断**：恢复时只检查 `docs/agent-work-state.md`、任务进度账本最近记录、当前 Spec/Plan 和账本列出的源码/测试文件；不要默认打开完整恢复卡、问题日志、milestones、详细状态、全量测试或模型响应。
- **修复**：新增中文 `tasks/task-progress.md`，规定每个子任务开始、完成或暂停时记录目标、文件、验证、阻塞和下一步；`scripts/resume_context.ps1` 默认只输出快照和该账本尾部，详细 `tasks/task-state.md` 改为兼容性按需读取。总体 Goal、`agent-work-state.md`、`task-resume.md` 和恢复卡均同步该规则。
- **预防**：恢复代理先读快照和最近进度，再按指针读取对应规划与待修改文件；阶段收口时才把稳定结论归档到历史文档。账本不得写入密钥、prompt、模型原文、私有路径或完整原始数据。
## M282 真实模型已到达但 v2 Composite Planner 输出仍需 fail closed

- **现象**：Docker 生产容器的真实模型短探测返回 HTTP 200，已生成 `spatial-agent.composite-request-context.v2`；但 Planner 结果为 `REJECTED/plan_response_field_invalid`，0 个组件且没有 `run_id`。
- **根因**：provider 可达和上下文生成成功，不等于模型遵守当前 Composite Planner 的顶层字段与 allowlist。真实模型可能输出未声明字段或包装结构，不能把 HTTP 200 当作合法计划。
- **诊断**：只记录 HTTP 状态、Planner status、有限 error code、context schema、context fingerprint 和组件数；不要读取或输出 prompt、响应原文、请求头、密钥或私有路径。分别验证 context、Planner contract 和 execution gate。
- **修复**：保留 v2 context 在 provider 前的 schema/预算校验；Planner 输出继续经过 canonical normalize、能力目录 allowlist 和字段校验；非法输出在创建 Composite run 前安全拒绝。
- **预防**：真实模型验收采用 provider → context → plan schema → canonical DAG → execution 分层；兼容中转格式只能通过有界 normalizer 增加，并用 fake/replay 回归，不能为一次 live 请求放宽未知字段。
## M283 planner evidence 接入时 helper 插入函数体导致 Docker 语法回归

- **现象**：新增 Composite planner evidence 持久化后，Docker 测试在导入 `agent/application/composite_runs.py` 时失败，报 `IndentationError`；此前的逻辑测试尚未开始执行。
- **根因**：使用局部补丁插入 `_safe_planning_evidence()` 时落在 `_run_status()` 的 `except` 分支中间，破坏了原函数的缩进结构。
- **诊断**：新增跨入口 helper 后必须先在 Docker 中执行 compile/import，再执行定向测试；“镜像构建成功”只代表文件已复制，不代表 Python 模块可导入。
- **修复**：把 helper 移到完整 `_run_status()` 函数之后，恢复 `except ValueError` 的返回分支；重建 Docker 后 M283/M278/M282 定向 **22/22** 通过。
- **预防**：对函数体附近做局部 diff 检查，优先运行 `compileall`；helper 插入不得截断控制流。测试失败时记录真正的语法/导入阻塞，不用删除测试绕过。

## M283 前端 projection 资源白名单与浏览器缓存导致验收假失败

- **现象**：新增前端结果 projection 后，源文件和首页引用已存在，但生产静态资源接口仍返回 404；资源白名单未同步时，浏览器无法创建 projection。白名单修复后，浏览器 smoke 首次仍读取旧缓存，误报 projection 未加载。
- **根因**：前端静态文件不是目录直出，而是由 `agent/web_assets.py` 的公共 allowlist 控制；浏览器 smoke 复用同一页面时又可能命中旧的 index 资源缓存。
- **诊断**：前端改动必须同时检查首页 script 引用、静态资源 HTTP 200、Docker 重建后的 allowlist 和浏览器实际 `document.scripts`；smoke 导航使用有界缓存破除参数，不读取模型或私有配置。
- **修复**：把 projection 文件加入 `WEB_ASSETS`，Docker 重建后资源和 readiness 均为 200；浏览器 smoke 导航增加缓存破除参数，并只验证阶段数量、关键发现和不展示隐藏工具名。
- **预防**：新增静态资源时将入口引用、allowlist、Docker 构建和浏览器 smoke 作为一个最小验收单元；不要用一次缓存命中的浏览器结果代表当前镜像。

## M283 地图 smoke 暴露清空对话后的空间上下文复位旧问题

- **现象**：M283-D projection 改动后的既有地图 smoke 中，点击“清空对话”后，地图实例、已选要素和 renderer context 仍短暂存在，导致“立即清空工作区”断言失败。
- **根因**：该问题发生在 GIS renderer 的清理/异步历史恢复接缝，不由结果 projection 读取或生成；projection 只新增结果区 DOM，不负责地图状态。
- **诊断**：独立检查 `rendererRegistry.context()`、地图实例和选中按钮状态；将其与 projection Node/browser contract 分开验收，避免把旧地图问题误判为 projection 失败。
- **当前处理**：本阶段不绕过断言、不把地图 smoke 标为通过；保留为 M283-E 的独立修复项，先完成跨入口结果验收。
- **预防**：后续清空会话的验收必须在同步 reset、异步 clear 请求和历史恢复三种时序下检查地图实例、空间上下文和结果工作区的一致清空。

## M283 恢复账本按文件尾部取记录导致最新任务被旧记录挤出

- **现象**：任务账本已将最新完成任务放在“最近完成”标题下方，但恢复脚本按整个文件尾部倒序选择记录，恢复后显示旧的 M283-B/C，而不是当前刚完成的 M283-E/D。
- **根因**：短账本的“最近完成”区块采用最新记录置顶策略，脚本却把它当作历史追加日志处理，记录顺序约定不一致。
- **诊断**：验证恢复输出时同时检查当前进行中任务和最近完成任务 ID；不能只确认脚本执行成功就认为恢复上下文正确。
- **修复**：`scripts/resume_context.ps1` 改为从“最近完成”区块顶部读取，保持有界字符预算；恢复输出现在包含 M283-E/D，并继续不读取历史档案、全量测试或无关源码。
- **预防**：任务账本明确采用“最新完成记录置顶”协议；每次阶段收口都运行一次无参数恢复 smoke，检查当前任务、待修改文件和最近完成任务是否一致。

## M284 地图 smoke 的初始化历史恢复覆盖测试 fixture

- **现象**：浏览器地图 smoke 在手工注入一个 GeoJSON fixture 后，页面显示历史运行的“当前 renderer 没有收到可绘制几何”，因此在点击矢量要素前失败。Node renderer contract 和生产资源均正常。
- **根因**：Console bootstrap 设置 domain ready 后，还会异步执行历史任务恢复；smoke 只等待 `sendChat` 存在，没有等待 bootstrap/domain readiness，也没有先建立空白会话边界。历史恢复完成后会回写 workspace，覆盖手工 fixture。
- **诊断**：只检查页面的 bootstrap/domain ready、结果标题、map surface 和 renderer context；不要把历史回写覆盖误判为 GeoJSON、Leaflet 或 reset 逻辑错误。浏览器 smoke 必须使用单一 CDP 页面并串行导航。
- **修复**：地图 smoke 等待 `window.__consoleBootstrapReady && window.__consoleDomainReady`，随后触发一次 `clearChat()` 建立空白会话边界，只等待可观察的同步 reset，再注入 fixture；不改变服务端历史语义，也不增加 GIS 专用生产分支。
- **验证**：Node reset contract、Docker plugin/projection smoke、compileall、architecture strict、readiness 通过；浏览器 map smoke 通过，Leaflet 图层 1 个、SVG 路径 4 个，选择和清空后即时/延迟空态均通过。
- **预防**：浏览器验收必须显式等待应用初始化信号，并在会话/历史可异步恢复的页面上先固定测试状态；不要用固定长延时替代 generation/reset 边界。

## M284 清空后的地图与旧异步 render 需要公共 reset boundary

- **现象**：清空对话后，地图实例、空间 selection 或旧的异步 render 可能继续存在或回写，前端工作区与会话状态短暂不一致。
- **根因**：Renderer adapter 自己拥有地图/selection 状态，而 Console 会话、领域和结果 projection 由另一层控制；没有统一的 adapter reset 通知和 generation 失效边界时，各 surface 的清理时序不一致。
- **诊断**：分别断言 `rendererRegistry.context()`、visual surface、Leaflet/SVG 节点、选择按钮和旧 render 返回状态；不能只断言消息列表被清空。
- **修复**：Registry 的 `reset(context)` 先递增 generation，再通知所有 adapter；GIS adapter 清理自己的地图实例、surface、selection 和按钮；旧异步 render 返回 `superseded`。Console 的清空、切换会话和切换领域复用同一 reset seam。
- **验证**：`console_reset_contract_smoke.js`、plugin renderer regression、map browser smoke 和 projection browser smoke 通过；未修改 Runtime、Planner、ToolRegistry、Result schema 或服务端 session 语义。
- **预防**：新增前端 renderer 必须提供 adapter-owned `reset/context` 契约；清理不可依赖网络或固定延时，且每阶段至少保留一个 stale-render 负向断言。

## M285 中转 Composite Planner 仍不能稳定生成合法组合计划

- **现象**：Docker 显式真实 Composite planning probe 到达 provider，但两次单请求分别返回 `plan_response_field_invalid` 和 `plan_components_unexpected`；两次均为 0 个组件、未创建 run。第二次已进入本地 outcome/组件校验，但非成功 outcome 仍携带组件。
- **根因**：中转 provider 的 JSON/模型输出没有稳定遵守 Composite Planner 的顶层字段、状态和组件契约；provider 可达不等于真实模型能生成合法多步计划。TaskPlan bridge、allowlist 和 Runtime 没有被错误归因。
- **诊断**：只记录 status、error_code、组件数、是否创建 run 和耗时；不读取或输出响应原文、prompt、请求头、密钥或私有路径。用脱敏 replay 验证两步 DAG，再用单次 live probe 验证真实模型契约。
- **当前处理**：收紧 Composite Planner 的系统指令，继续保留本地严格字段/状态校验；非法输出在创建 run 前拒绝。M285 的两步 replay、HTTP/async evidence、artifact/restart 恢复均已通过，真实中转失败作为下一阶段模型适配问题保留。
- **预防**：不能为一次 live 请求放宽未知字段或接受非成功组件；后续模型适配只能增加有文档、有回放、有边界的格式兼容，并保持 Rule/Replay/LLM 共享 TaskPlan 门控。默认 CI 不访问 provider。

## M285 真实模型的四类失败必须分层记录

- **现象**：在同一套有界 Docker live probe 中，真实中转先后出现 `plan_response_field_invalid`、`plan_components_unexpected`、`taskplan_policy_unavailable` 和 `capability_not_registered` 四类结构化拒绝；每次均为单请求、0 个工具步骤、未创建 execution run。
- **根因区分**：前两类是 provider 输出字段/状态契约不稳定；第三类暴露了本地 capability projection 漏掉 `tools` 字段，使合法计划无法建立 TaskPlan 工具 allowlist；第四类是模型选择了能力目录之外的 capability，说明本地 allowlist 正确阻断了越权计划。
- **修复**：Composite Planner 明确要求成功必须有非空组件，澄清/拒绝必须为空组件；`_candidate_projection()` 补齐受限 `tools` 投影；live probe 增加 `--max-output-tokens`（64～4096，默认 128），复杂请求可显式提高输出上限。未知能力、字段和非成功组件约束继续 fail closed。
- **验证**：离线 replay、TaskPlan bridge、HTTP/async/artifact/restart evidence 和 M283/M285 精简回归继续通过；live 只记录状态、错误码、步骤数、是否创建 run 和 token/耗时摘要，不保存 prompt、模型原文、密钥或私有路径。
- **预防**：provider readiness、context projection、Planner schema、TaskPlan allowlist 和 execution 必须作为独立验收层；真实模型适配只能在 provider adapter/提示契约层做有界兼容，并用脱敏 replay 固化，不得为一次 live 成功放宽 Runtime 或工具权限。

## Live probe 的输出预算没有传到懒加载的 Composite Planner

- **现象**：`scripts/live_provider_probe.py` 已增加 `--max-output-tokens`，但 Composite planning application 在生产 Composition Root 中按 `planner=openai` 懒加载客户端；只修改局部 `config` 不会影响真正的 Composite 请求，复杂计划仍可能使用环境默认预算。
- **根因**：provider connectivity probe 直接接收 CLI 构造的 client，Composite probe 则在导入 `production_api` 后由 `_composite_planner_factory` 重新读取环境配置，两个路径的配置注入边界不同。
- **修复**：Composite 分支在导入/调用生产组合器前，把经过 64～4096 限制的输出预算写入当前进程的 `OPENAI_MAX_OUTPUT_TOKENS`；没有修改默认生产环境或 Runtime 生命周期。
- **验证**：Docker 重建后 M286-B 紧凑 contract **3/3** 通过；live 仍保持单请求、0 重试和脱敏 receipt。
- **预防**：显式验收 CLI 参数必须沿实际 Composition Root 生效；新增 provider 参数时同时检查 direct probe、懒加载 planner 和 HTTP/production 入口，不能只测试局部 client factory。

## M286 中转模型到达 provider 后仍携带未声明组件字段

- **现象**：带明确区域和目标的 Composite live probe 已到达 `openai` Planner，但本地结果为 `REJECTED/plan_component_field_invalid`；0 个组件、未创建 run。此前一条缺少区域事实的请求在 context 层返回 `NEEDS_CLARIFICATION`，同样未创建 run。
- **根因**：provider 可达、上下文身份提示和输出预算生效，并不代表模型会严格遵守组件字段 allowlist；当前脱敏 receipt 不能包含模型原文或未知字段名，因此不能据此猜测兼容字段。
- **处理**：继续拒绝未知组件字段，保留 `plan_component_field_invalid` 和 `planner_source=openai` 的安全 evidence；不把未知字段加入 schema，不绕过 TaskPlan/ToolRegistry 门控。下一阶段研究一次有界 schema 修复回合或明确的 provider adapter 映射，并先用 replay 固化。
- **验证**：阶段联合 Docker contract **17/17**、compileall、architecture strict、readiness 200 通过；两条 live 输入分别验证前置澄清和 provider 到达后的 schema fail-closed。
- **预防**：真实模型验收按 context → provider → response schema → capability allowlist → TaskPlan → execution 分层；任何兼容新增都必须有脱敏 replay、字段白名单和无越权负向断言，不能为了 live 通过接受任意组件字段。

## M287 单次 Planner repair 仍返回非法结构，不能扩大重试预算

- **现象**：真实中转 Composite live 首次返回 `plan_component_field_invalid` 后触发一次 repair；repair 仍未通过同一 schema 校验，最终保持 `REJECTED/plan_component_field_invalid`，receipt 为 `attempted=true`、`count=1`、`status=failed`，0 组件且未创建 run。
- **根因**：repair 只能提醒模型修正结构，不能改变 provider 对严格 schema 的遵循能力；继续增加次数会放大 token、延迟和重复提交风险，也不能保证输出合法。
- **修复**：M287 建立 `spatial-agent.planner-repair-request.v1` 与 `planner-repair-lineage.v1`；仅允许有限 schema 错误进入一次 repair，repair 后重新走 normalize、capability allowlist、TaskPlan bridge；live harness 和 async/artifact evidence 均只保存安全 lineage。
- **验证**：M287/M286/M285/M283 联合 **23/23**、compileall、architecture strict、readiness 200、前端 projection smoke 通过；真实 repair probe 只发生一次修复调用，无 execution run。
- **预防**：下一阶段优先做 provider wire-level structured-output 能力协商和脱敏 replay，不增加 repair 次数，不接受未知字段或未知能力，不把失败伪装为成功。

## M288 Provider wire mode 与旧 client seam 的兼容边界

- **现象**：为 Composite Planner 指定 `schema_name` 关键字后，旧的离线 replay/fake client 因只实现两参数 `complete_json(messages, schema)` 而失败；同时中转 provider 对 strict schema 与 JSON object 的支持并不一致。
- **根因**：wire mode 属于 provider client 能力，不应通过扩大公共 Planner client 方法签名向所有 Domain/测试适配器传播；provider 可达也不代表应用层 schema 已被执行。
- **修复**：新增版本化 `provider-structured-output.v1` profile；默认使用 strict `json_schema`，显式配置才使用 `json_object`，`unavailable` 在网络请求前 fail closed。Composite Planner 保持原有两参数 client seam，所有返回仍经过本地 response/schema、能力 allowlist 和 TaskPlan 门控。
- **验证**：M288/M279/M286/M287 集中 Docker contract **25/25**；live provider probe `READY`，Chat Completions、`json_schema`、schema enforced、1 请求 0 重试；未保存模型原文、prompt、密钥或私有路径。
- **预防**：新增 provider wire 兼容时优先在 client profile/adaptor 内收口；不得仅为命中真实模型而改动公共协议、放宽 unknown fields 或增加 repair 次数。前端只消费脱敏 structured-output evidence，不显示 provider 原始响应。

## M289 真实 Composite Planner 规划请求在 45 秒内超时

- **现象**：Docker 中一次明确的 GIS + Economic Composite planning probe 使用真实中转模型和 1024 输出预算，最终返回 `FAILED/timeout`、0 组件、无 request fingerprint、未创建 execution run。
- **根因分类**：provider connectivity probe 已在同一配置下 `READY`，因此本次不是简单网络不可达；当前只能将其归类为真实 Composite 规划延迟/响应未完成，不能推断模型原文或业务数据原因。
- **处理**：保持 planning deadline、schema、能力 allowlist 和 TaskPlan gate 不变；M289 增加跨状态 matrix 与 `execution_run_created` 脱敏 receipt，方便区分成功、澄清、拒绝和超时。
- **验证**：M289 matrix + M280 contract **7/7**；规则模式可结构化澄清且不创建 run；live 只记录 timeout、组件数、wire/metric 摘要，不保存 prompt、模型原文、密钥或路径。
- **预防**：后续若调整 live deadline，必须只在显式 acceptance harness 中调整并保留单次请求边界；不能通过无限等待、自动重复请求或放宽输出 schema 把 timeout 伪装成成功。

## M290 真实模型语义上报 success 但组件为空

- **现象**：真实 provider 的 structured output 请求成功返回，但 Composite 结果语义为 `success` 时没有任何组件；如果直接信任状态，后续无法生成 Domain workflow 或 TaskPlan。
- **根因**：wire/schema 合法只说明字段形状可解析，不代表模型给出了可执行的完整计划；Composite 的 success 还必须满足组件数量、能力身份和可物化 workflow 条件。
- **处理**：保留统一的 `plan_components_required` 语义门控；空组件在 TaskPlan 和 execution run 创建前拒绝，记录有界 planner/provider/deadline evidence，不保存模型原文或 prompt。组件 preview 使用按 Domain 隔离的稳定 session，并优先复用已发现的 Domain workflow。
- **验证**：M290/M282/M279/M289/M286/M287 Docker 集中 **41/41**；provider timeout、harness timeout、预算越界和 Domain session 隔离均有回归，真实模型结果保持单次、脱敏、无 execution run。
- **下一步**：M291 建立版本化 plan completeness contract，检查 capability → workflow → ToolRegistry/result types → TaskPlan 的完整闭合，并将语义澄清/拒绝投影到所有入口。

## M291 真实模型组件在 Domain preview 阶段缺少事实时被错误显示为拒绝

- **现象**：M291 显式 live probe 中 provider structured output 成功，模型返回了可识别组件，但组件 materialization 的 Domain preview 返回 `taskplan_component_clarification`；原应用状态被投影为 `REJECTED`，容易让用户误以为能力或权限被拒绝。
- **根因**：Planner 失败状态映射只覆盖 provider failure、空组件和 capability unavailable，没有把 TaskPlan materialization 的“需要补充事实”错误码归入澄清状态。
- **修复**：将 `taskplan_component_clarification` 纳入 `NEEDS_CLARIFICATION` 映射；继续保留统一 TaskPlan/ToolRegistry gate，不创建 execution run，不重试 live 请求。
- **验证**：真实 probe 单次、0 重试、provider structured output `success`、0 execution run；完整 Python contract 已通过，修复后只需执行离线状态映射回归，不重复真实调用。

## M292 组件事实不足需要从 Planner 传递到 Domain preview

- **现象**：Planner 已选择合法 capability，但 Domain preview 仍缺少指标、区域或其它公共事实；如果继续从组件文本重新猜测，容易绕过统一 RequestFacts、产生不一致的澄清，或把事实缺失误报为拒绝。
- **根因**：能力 requirements、RequestFacts、workflow constraints 和 preview 参数此前没有一个有界公共交接对象；单个 Domain 只能看到自己的局部解析结果，Planner 也无法安全保留组件身份。
- **修复**：新增 `spatial-agent.component-fact-handoff.v1`，仅投影版本、组件/领域/能力身份、公共 requirements、known facts、workflow constraints、missing fields 和 next actions；ready handoff 才进入 Domain preview，仍必须生成 canonical TaskPlan 并通过原有门禁。
- **验证**：M292 compact contract 覆盖缺失事实、补充后 Domain preview 和字段状态；未将 Domain 私有模型或原始请求扩散到公共 Runtime。
- **预防**：新增能力优先声明公共 requirements；不要在 Runtime 中增加区域/问句判断，也不要让 preview 直接信任 Planner 携带的私有 handoff。

## M292 单组件 continuation 不能被当作多组件澄清

- **现象**：一个 Composite 请求同时选择多个组件时，单组件 continuation 只能绑定一个 component identity；如果直接复用，补充一个组件可能丢失其它组件的选择或让重新规划静默换组件。
- **根因**：M292 的目标是稳定单组件事实交接和可恢复续跑，token payload 只绑定一个组件；多组件补充事实、组件集合稳定性和部分完成状态还没有公共契约。
- **处理**：M292 保持单组件 token 的字段白名单、签名、过期和 fail-closed 语义，不伪装成多组件支持；M293 单独设计组件集合 handoff 与按 `component_id` 分组的 continuation。
- **预防**：多组件 continuation 必须同时绑定原 request fingerprint、Planner selection fingerprint、组件集合和字段白名单；集合漂移、未知组件或未知字段不得自动修复。

## M292 严格 TaskPlan gate 暴露旧 replay fixture 缺少 workflow

- **现象**：集中运行 M292 与相邻 Planner 回归时，旧 M285/M283 replay fixture 中只有 component identity，没有可物化的 workflow/task plan，结果从 `PLANNED/QUEUED` 变为 `REJECTED/plan_completeness_failed`。
- **诊断**：这是测试 fixture 与 M291 新契约不一致，不是放宽生产门禁的理由；先查看 `error_code` 和 `task_plan_bridge`，再区分 fixture 缺失与实际 Planner 回归。
- **修复**：为旧 fixture 增加最小已注册 tool、result type 和 canonical one-step workflow；生产代码继续拒绝 deferred/不可物化组件。
- **验证**：Docker 重建镜像后 M292 compact **3/3** 与相邻回归 **19/19** 通过。
- **预防**：新增 replay/fixture 必须显式提供 capability → workflow → TaskPlan 闭合链；阶段回归集中运行，不能只运行局部 M292 测试就宣称相邻契约未受影响。

## M293 多组件澄清不能为每个组件分别签发 token

- **现象**：一个开放式请求同时选择多个组件并分别缺少事实时，为每个组件单独签发 continuation 会产生多个互不关联的续接入口；补充一个组件后可能丢失其它组件的 selection 或让 Planner 静默换组件。
- **根因**：M292 的 continuation identity 只绑定单个 component/domain/capability；多组件请求需要绑定完整组件集合和全局 Planner selection fingerprint。
- **修复**：新增 `spatial-agent.composite-fact-handoff.v1` 和 `spatial-agent.composite-clarification-continuation.v1`；一个 handoff 只产生一个 token，事实按 `component_id` 分组，再按 Domain 合并进入 context。
- **验证**：M293 compact 覆盖全部补充、部分补充、未知组件拒绝、HTTP prepare round-trip；重新规划后仍要求同一组件集合和 TaskPlan gate。
- **预防**：多组件 token 只保存 identity、字段白名单和过期时间；组件集合漂移、未知字段和未声明组件必须 fail closed，不通过增加 repair 次数解决。

## M293 多组件安全投影不能沿用单组件字段结构

- **现象**：如果跨入口继续只投影 `component_id/domain_id/field_ids`，多组件 continuation 的 identity 会在 artifact、View 或前端被截断，用户无法知道哪一部分待补充。
- **根因**：旧 safe projection 是为 M292 单组件设计，未声明 `component_ids`、`domain_ids` 和组件摘要数组。
- **修复**：planning evidence、Composite View、TaskPlan bridge 和 Console projection 增加有界组件摘要；只保留 identity、字段标签和状态，严格过滤 token 与模型内部内容。
- **验证**：Node projection 增加多组件澄清案例；Docker 合并回归 **26/26**、compileall、architecture strict、readiness 200 通过。
- **预防**：新增版本化投影字段时必须同时检查同步 HTTP、异步/artifact/restart、View 和前端；前端不根据 Domain 或工具名增加分支。

## M295 Docker 生产镜像不挂载源码，修改后测试不可见

- **现象**：宿主机新增 M295 测试后，直接用既有 `docker compose run` 执行时提示找不到测试模块；容器仍使用旧的生产镜像，容器内没有实时源码挂载。
- **根因**：`docker-compose.prod.yml` 的生产服务采用镜像内 `/app`，不是开发目录挂载；重建宿主机文件不会自动更新已创建容器或旧镜像。
- **处理**：代码或测试变更后，先执行 Docker image build，再按需 `up -d --force-recreate` 更新服务；阶段测试统一在新镜像中执行。
- **验证**：重建后 M295 compact **5/5**、合并回归 **30/30**、compileall、architecture strict、Node projection smoke、生产 readiness 200 和 HTTP receipt 验收通过。
- **预防**：恢复工作时先确认镜像是否包含当前提交；生产 Docker 默认不挂载源码，避免把旧容器的绿色结果当作当前代码证据。

## M295 脱敏 discovery 摘要在 View 中丢失计数

- **现象**：Planner evidence 已保存 discovery receipt 的候选/数据需求计数，但经过安全投影后 Composite View 只从候选明细数组计数，用户看到候选数为 0。
- **根因**：View 投影只考虑完整 receipt，不兼容 async/artifact 边界传递的摘要形状；这属于投影契约不完整，不是数据为空。
- **修复**：`Composite View` 优先读取已验证的摘要计数字段，同时保留候选数组路径；新增 M295 contract 覆盖 planning evidence → View 的 discovery identity 和计数一致性。
- **验证**：M295 compact **5/5**、前端 projection smoke 和合并回归 **30/30** 通过；未扩大 receipt 或暴露模型/私有字段。
- **预防**：新增结构化证据字段时同时设计完整对象、脱敏摘要、View、Artifact 和前端的投影矩阵；不要在消费端假设上游始终保留明细。

## M295 真实模型 structured output 可达但跨域计划仍需澄清

- **现象**：Docker 真实模型 probe 单次请求、0 重试，structured output 通道成功，但跨 `gis + economic` Composite 规划返回 `NEEDS_CLARIFICATION`，0 组件、未创建 execution run。
- **根因分类**：provider wire/schema 可用不等于请求事实完整或模型一定能生成合法多组件计划；当前 evidence 只能证明通道与安全门禁，不证明 live 业务规划成功。
- **处理**：保留 `spatial-agent.analysis-discovery.v1`、`needs_facts/request_facts_missing` 和 Planner fail-closed；不保存模型原文、不放宽组件字段、不增加 repair 次数、不创建 run。
- **验证**：真实模型单次显式探测耗时约 18.6 秒，structured output `json_schema` 成功，安全返回澄清；规则/HTTP 真实 Docker 入口同时保留 discovery/request fingerprint 和中文缺失字段。
- **预防**：将 live 成功、澄清、不可用分开验收；只有在 catalog、RequestFacts、workflow、TaskPlan 和 execution binding 全部闭合后，才允许真实跨域执行进入下一阶段。

## M296 Composite context 过度截断候选工具

- **现象**：GIS 的 `spatial_analysis` 已声明 9 个工具，但 Composite Request Context 只透传前 8 个；真实 TaskPlan bridge 因缺少最后一个工具而返回 `taskplan_tool_not_allowlisted`，容易被误判为 workflow 或模型规划失败。
- **根因**：候选工具投影和 TaskPlan bridge 使用了不同的有界容量，context 的旧容量没有随着能力目录扩展同步调整。
- **修复**：将 context 的候选工具上限与 bridge 使用的有界容量统一为 24；新增完整 9 工具透传回归，保持有界、去重和安全过滤。
- **验证**：Docker M296 定向 **9/9**；GIS 9 个工具完整透传，跨 GIS/Economic 的 Replay 计划、binding、同步/异步执行和恢复均通过；未扩大为无限上下文。
- **预防**：凡是新增目录能力或工具，必须同时核对 catalog、context、planner、TaskPlan bridge 的容量常量，并用“最大声明数量”做一次回归；不能只提高单一消费端上限。

## M297 Planner catalog 增加结果类型后超过旧上下文预算

- **现象**：向 Planner-facing catalog 增加按 Result Registry 投影的 `output_profiles` 后，GIS + Economic 目录投影从约 64 KiB 增长到约 77 KiB，旧的 64 KiB 上限导致跨域规划在目录阶段直接失败。
- **根因**：新增的是已有公共契约的必要类型信息，不能通过截断 profiles 恢复，否则模型会失去判断 vector/metrics/timeseries 的依据。
- **处理**：将 Composite capability projection 的有界上下文上限与 Request Context 对齐到 96 KiB；仍限制 Domain、capability、workflow、tool 和 profile 数量，不接受无限增长。
- **预防**：扩展 Planner-facing 结构化投影时，先测量代表性多领域目录的编码大小，再同步调整有限预算并保留超限 fail closed；不要静默丢弃类型或来源字段。

## M297 Planner 上下文预算与目录投影不一致

- **现象**：M297 将 Composite capability projection 和 Request Context 的有界预算提高到 96 KiB 后，真实模型验收仍在本地 Planner 门禁返回 `planner_context_too_large`，请求尚未发给 provider。
- **根因**：能力目录投影预算已扩展，但 `LLMCompositePlanner` 仍保留 64 KiB 的独立硬编码上限，公共边界出现两个互相矛盾的容量契约。
- **修复**：将 LLM Planner 的 context 校验与公共 Composite Context 对齐到 96 KiB；仍保留字节预算和 fail-closed，不接受无限上下文。修复后 live 请求到达 provider，structured output 返回安全澄清。
- **验证**：Docker M297/M298 相关回归 **55/55**，compileall、architecture strict、Node projection smoke 和 readiness HTTP 200 通过；真实请求未保存模型原文。
- **预防**：新增或调整目录投影预算时，必须同时检查 Context Builder、Planner、provider payload 和恢复边界；用代表性多领域目录做一次端到端预算检查。

## M298 产品默认模式污染低层离线 HTTP 测试

- **现象**：为让产品默认使用真实模型与本地数据，`HTTPApplication` 曾在所有调用上注入 `openai + local`，导致直接 Application 单测从确定性的 `rule + memory` 变成依赖网络和本地 GIS 的路径，出现澄清和 fingerprint 不一致。
- **根因**：产品默认配置的注入边界放在了共享语义应用内部，而不是 FastAPI/stdlib 产品入口；低层应用、测试替身和产品入口没有区分调用语义。
- **修复**：`HTTPApplication` 增加显式 `use_product_defaults` 开关，生产 FastAPI/stdlib 入口显式启用；低层调用保留 `rule + memory` 回退，显式传入值始终优先。Composite 组件只继承同一顶层选择。
- **验证**：Docker M298 及相邻契约 **55/55**；compileall、architecture strict、Node projection smoke、生产 readiness HTTP 200 通过。
- **预防**：产品默认只能在产品边界注入；共享 Application、Domain Service 和单测不得读取产品默认环境变量。任何默认值变更都必须同时覆盖“产品缺省”和“低层离线显式/隐式”两条路径。

## M298 可选 discovery 未声明被误判为数据不可用

- **现象**：旧 Domain 测试替身未声明可选 `discover()` 时，已注册且执行契约有效的能力被 Composite Planner 返回为 `NEEDS_CLARIFICATION/data_unavailable`。
- **根因**：Context Builder 已允许使用有界能力目录作为 discovery 来源，但 Discovery Gateway 状态聚合仍把 `not_declared` 与显式 `unavailable` 合并处理。
- **修复**：未声明 discovery 视为目录回退，不阻断可用候选；只有 discovery adapter 显式失败才进入数据不可用状态。未知执行契约仍不会穿过执行就绪门禁。
- **验证**：M279/M282/M296/M297/M298 合并回归通过；未放宽工具、workflow、TaskPlan 或 execution binding 校验。
- **预防**：状态机必须区分未声明、未知、显式失败和数据缺失；新增状态时同步检查 discovery receipt、clarification、Planner 和恢复投影。

## M299 Planner 将完整内部上下文直接发送给真实模型

- **现象**：产品默认切换到真实模型后，Planner 仍把包含重复目录、领域上下文、workflow 和 discovery receipt 的完整 Context 序列化到 provider payload；多领域请求容易接近预算，模型还要从重复结构中自行辨认可选能力。
- **根因**：Runtime 校验/恢复所需的完整上下文与模型选择所需的最小上下文没有独立边界，Context Builder、LLM Planner 和 provider payload 各自维护投影语义。
- **修复**：新增领域中立 `spatial-agent.planner-envelope.v1`，将 provider 输入分成请求事实、能力索引、选择摘要和候选执行契约四层；保留结果类型 profile、workflow、readiness 和候选 identity，过滤私有字段与无关 workflow。统一使用 96 KiB 有界预算并超限 fail-closed。
- **验证**：Docker M299/M297/M298 **18/18**，受影响 M282/M286/M287 **19/19**；provider payload 不含测试私有路径，选择候选外的 workflow 不进入执行层。
- **预防**：后续扩展 Planner context 先判断字段属于“模型选择”还是“Runtime 证据”，只通过 envelope 增加有界投影；完整 Context 不得直接作为模型输入，也不得为了成功静默截断关键 identity、data profile 或 readiness。

## M299 选择证据存在于后端但前端难以直接理解

- **现象**：Planner evidence 原先只有状态、数量和能力 ID；前端如果直接展示这些字段，会出现程序化信息过多，用户看不出系统选择了什么、为什么等待或下一步要补什么。
- **根因**：选择结果、候选能力的 data profile/readiness、澄清信息和 next actions 没有一个共同的用户安全投影；后端与前端只能各自猜测字段含义。
- **修复**：新增领域中立 `spatial-agent.selection-evidence.v1`，由 planning attach seam 统一生成；前端仅展示能力标签、可用状态、澄清文案和下一步动作，内部 capability ID、workflow ID 和模型原文不进入用户主视图。
- **预防**：前端新增结果类型或阶段时先消费结构化 evidence，不能按工具名或专题分支拼文案；success、clarification、data unavailable 和 provider failure 必须保持可区分。

## M299 选择证据在运行恢复链路中被安全白名单丢弃

- **现象**：planning attach 已生成 `selection-evidence.v1`，但 CompositeRunApplication 的持久化白名单未包含该字段；同步执行、异步 worker 或 artifact/重启读取后，Composite View 无法展示能力选择摘要。
- **根因**：新增 evidence 只接入了规划响应和前端入口，没有同步检查 safe persistence projection 与 Composite View projection。
- **修复**：将选择证据加入安全白名单，增加版本化 normalize seam，并由 Composite View 的 planning projection 统一输出；不传递模型原文或私有字段。
- **预防**：每个新 evidence 字段必须沿“规划响应 → 同步/异步持久化 → artifact/重启 → View → 前端”矩阵验收，不能只验证首次 HTTP 响应。

## Economic 自然语言区域提取误把指标词识别为区域

- **现象**：`查询洪山区地区生产总值` 被提取为 `查询洪山区` 和 `地区` 两个区域，真实数据查询返回 `economic_region_unavailable`。
- **根因**：区域正则会捕获查询动词前缀以及指标名称“地区生产总值”中的“地区”，事实提取层没有去除通用指令前缀和指标词噪声。
- **修复**：在 Economic Domain 的区域事实提取中清理通用中文指令前缀、连接词，并过滤独立的“地区/区域”；不增加洪山区专用分支。
- **预防**：真实数据验收至少包含自然问法和显式 ID 问法；应先检查 `request_facts.entities.regions`，再判断数据源是否缺失。

## M299 真实模型中转请求超时不能等同于未启动 Agent

- **现象**：显式 live Composite 探测已进入真实 provider 配置，但在 45 秒 harness deadline 内返回 `timeout`，未创建 execution run。
- **根因分类**：当前有效配置是中转地址 `opencode.ai/zen/go/v1` 与 `deepseek-v4-flash`；provider 超时属于外部模型/网络可达性问题，不能据此把 Runtime 的默认 Agent 开关判定为未启动。
- **处理**：保留 `openai + local` 产品默认和 fail-closed 超时结果；只记录状态、deadline 和是否创建 run，不保存模型原文或密钥。后续 live 验收需单独区分 provider timeout、结构化澄清和成功计划。
- **预防**：前端应在规划阶段显示“正在连接模型/等待规划结果”，超过 deadline 后给出可恢复提示；离线 Rule/Replay 验收不能伪装成真实模型成功。

## M299 同步 Composite 响应缺少即时 View

- **现象**：同步执行返回了 canonical Result，但没有直接返回 Composite View；异步轮询或再次读取时才生成 View，导致首次前端渲染与恢复路径不一致。
- **根因**：View 只在 `get_run` response seam 生成，`_execute_and_persist` 的同步返回路径未复用同一投影函数。
- **修复**：同步、异步 worker 返回体均直接附带 `spatial-agent.composite-view.v1`；选择 evidence 和结果视图因此无需二次请求即可展示。
- **预防**：跨入口验收必须分别检查“首次返回”和“恢复读取”两个时点，不能只比较最终 SQLite/artifact 结果。

## M299 异步完成状态早于 artifact 发布

- **现象**：异步请求显式要求导出 artifact 时，轮询偶尔先看到 `COMPLETED`，但响应中还没有 `artifact_ref`；此时用户会误以为证据或导出失败。
- **根因**：Composite 执行先保存完成状态，随后才写 artifact 并回写引用；SQLite/内存轮询存在一个可观察的中间窗口。
- **修复**：调整发布顺序，先完成 artifact 写入并获得引用，再把最终 `COMPLETED` 快照写入状态存储；增加阻塞 artifact store 的时序回归，确保不会暴露不完整终态。
- **验证**：Docker 最小时序回归通过；M299/M263 合并回归 **19/19**，compileall、architecture strict、Node projection smoke 和 readiness 通过。
- **预防**：任何“终态 + 外部证据”组合都必须定义原子可见性顺序；异步轮询测试应覆盖证据发布中的中间窗口，不能只验证最终读取。

## M300 Composite 默认答案仍停留在模板摘要

- **现象**：产品入口已默认选择 `openai + local`，但 Composite 答案生成器只有在显式 live 环境变量开启时才注入；正常 LLM 规划成功后，用户仍看到组件数量等程序化模板摘要。
- **根因**：答案生成的启用条件与 Planner 选择脱节，默认 Agent 的模型规划结果没有传递到答案生成策略；为保护离线测试保留的 live gate 被误用成了产品默认 gate。
- **修复**：产品入口在存在模型配置时注入结构化 Composite 答案生成器；运行层只对带有 LLM Planner evidence 的结果调用它，Rule、Replay、直接执行和未配置模型继续离线回退；增加 `SPATIAL_AGENT_DISABLE_LLM_ANSWER=1` 作为部署关闭开关。
- **预防**：默认产品路径与测试路径分开验收；答案生成必须以结构化 Planner evidence 判定调用资格，不能根据用户文本或工具名猜测，也不能让答案模型修改事实和执行结果。
## M300 provider 失败被误投影为事实澄清

- **现象**：真实模型请求因中转/provider 失败时，规划响应状态为 `NEEDS_CLARIFICATION`，用户会看到“补充信息或调整问题”，但请求事实并未缺失。
- **根因**：Composite planning 的历史状态映射把 `planner_provider_failed` 与事实不足共用澄清状态，未向前端提供可重试的失败证据。
- **修复**：provider 失败现在返回 `FAILED`、`failure.v1`（`phase=planning`、`category=provider`、`retryable=true`）和“稍后重试”动作；事实澄清、能力不可用和 provider 故障仍通过不同错误码/证据区分。
- **验证**：新增 M300 精简契约；未放宽 Planner schema、能力 allowlist、TaskPlan 或 execution binding，也未保存模型原文和密钥。
- **预防**：状态、错误码、failure evidence 和 next action 必须成组设计；不能仅因前端需要一个“可处理状态”而把外部依赖故障伪装成用户事实缺失。

## M301 内部上下文与模型上下文共用预算导致真实目录误报超限

- **现象**：真实 GIS + Economic 多领域规划在 Context Builder 阶段返回 `context_budget_exceeded`；测量显示完整内部 Context 约 104 KiB，而实际 provider Planner Envelope 仅约 25.8 KiB。
- **根因**：内部 Context 同时保留执行、恢复、证据和 provider 投影，仍沿用 96 KiB 的模型预算；其中 `catalog_consistency` 的完整 binding/violation 明细又与候选和执行契约重复。
- **修复**：将内部 Composite Context、能力目录投影和 discovery receipt 的默认上限提升为 256 KiB；provider Planner Envelope 继续独立保持 96 KiB。内部一致性只保留计数和状态摘要，候选/TaskPlan/binding 继续承担逐项执行门禁。
- **验证**：真实双领域内部 Context 约 95.4 KiB、内部上限 256 KiB、provider Envelope 约 25.8 KiB；Docker M301/M300/M295/M294/M278 精简回归 **25/25**，compileall、architecture strict 和 readiness 通过。
- **预防**：不要简单放大模型输入；下一阶段按 `discovery / selection / execution` 规划阶段建立 provider context profile，诊断字段只进入 Runtime evidence，不默认发送给模型。

## M301 无关 Domain 缺失事实覆盖 Planner-first 语义

- **现象**：GIS 事实完整、Economic 事实缺失时，顶层 clarification 仍返回 `required`，阻断了 Planner；同时旧 discovery receipt 的澄清结果会覆盖 Context Builder 的 readiness 投影。
- **根因**：缺失事实被按所有启用 Domain 聚合，且旧兼容投影没有识别 `fact_readiness`；候选投影缺少 `execution_ready` 时也被错误视为不可选择。
- **修复**：新增领域中立 `request-fact-readiness.v1`，区分 `complete/partial/missing/unavailable`；仅当存在完整且可供 Planner 观察的候选时，将无关 Domain 缺失降为 `advisory`。合并澄清时只允许 `required → advisory` 的安全升级，保留数据/能力不可用等更具体状态；未显式声明 `execution_ready` 的旧候选仅用于观察，最终执行仍必须通过 TaskPlan/binding 门禁。
- **验证**：M301 无关事实回归与 M295 旧澄清/不可用回归通过；未降低 selected-component、ToolRegistry、workflow 或 execution binding 的执行约束。
- **预防**：事实 readiness 只能影响 Planner 观察和澄清层级，不能直接成为执行授权；每个兼容合并点必须保留更具体的不可用原因码。

## M302 Planner Envelope 仍混入跨阶段和重复上下文

- **现象**：M301 虽已将完整 Runtime Context 与 provider 预算分开，但模型输入仍同时包含 discovery、选择、完整 workflow binding 和重复的 result profile；96 KiB 上限没有区分“当前决策需要什么”。
- **根因**：Envelope 只有字段分层，没有生命周期阶段语义；Context Builder、LLM 初次规划和 repair 都使用同一投影，导致 Runtime 诊断信息与模型选择信息混在一起。
- **修复**：为公共 `spatial-agent.planner-envelope.v1` 增加 `projection_stage`，支持 `discovery`、`selection`、`execution`、`repair`。Context Builder 保存 discovery 摘要；LLM 规划重投影 selection，结构修复重投影 repair；execution/已有选中项的 repair 只保留选中能力、workflow、readiness、result profile 和事实缺口；不改变 Runtime 内部 Context、TaskPlan、ToolRegistry 或 execution binding 门禁。
- **验证**：Docker M302 及相邻 Planner/repair 回归 **34/34**，compileall、architecture strict、Service smoke 和 readiness HTTP 200 通过；示例投影大小为 discovery 2.95 KiB、selection 4.32 KiB、execution 3.46 KiB；未保存模型原文、密钥、私有路径或原始数据。
- **预防**：新增模型上下文前先标注所属阶段和用途；Runtime 证据字段不能因为“可用”就默认进入 provider payload。阶段投影必须保留 request identity、readiness、workflow 和 result profile，并对超预算 fail closed；尚未形成可信组件时，repair 只能使用有限候选并保持一次尝试。

## M302 旧 Docker 容器导致新增回归出现假绿灯

- **现象**：宿主机已经修改了 M302 测试和 execution binding，但直接在运行中的 Docker 容器执行回归时，新增测试没有出现在输出中；旧测试全部通过，无法证明当前工作树已被验证。
- **根因**：生产 compose 镜像通过 `COPY . /app` 固化源码；容器不会自动同步宿主机的新增文件。仅重启旧容器也不会更新镜像内容。
- **修复**：阶段收口前使用生产 compose 从当前工作树重新 build，再 `up -d --force-recreate`；确认容器 healthy 后才运行定向回归、compileall、architecture strict、Service smoke 和 readiness。
- **预防**：任何 Python 源码或测试改动后，不采纳未确认源码版本的旧容器结果；至少核对镜像重建日志和新增测试数量，避免旧容器制造假绿灯。Docker 是项目 Python/GIS 的统一验收环境。

## M302 execution projection 只记录组件身份导致 binding 描述漂移

- **现象**：execution projection 已经位于 binding 之后生成，但如果只比较 component_id/domain_id，调用方仍可能用相同组件 ID 搭配不同 capability 或依赖关系，造成“实际绑定执行内容”和“阶段证据描述”不一致。
- **根因**：execution binding 的旧组件身份没有保存 capability_id；plan fingerprint 也没有覆盖该能力身份，projection 只能验证有限的外部字段。
- **修复**：新生成的 execution binding 保存 capability_id，并把它纳入新的 plan fingerprint；execution projection 在生成时严格比较组件集合、顺序、领域、能力、依赖和 required，Envelope 白名单同时接纳 `execution_identity`，证据只保留有界 receipt。
- **预防**：凡是由已验证对象生成的阶段投影，都必须比较完整的可执行身份；不能把一致性检查降级为“只记录 fingerprint”。兼容旧 binding 时缺失字段保持可读，但新 binding 必须 fail closed 地闭合身份。

## M302 结果投影的 workspace/View 面板声明漂移

- **现象**：生产 HTTP 验收中，结果 View 含有 `map` 面板，但 workspace 面板清单为空，跨入口契约失败。
- **根因**：GIS Registry 为结果声明了 `ViewSpec(map)`，但公共 workspace 只登记显式业务 panels；结果 fallback 又按 ViewSpec 补出了不可用面板，形成两个来源不一致。
- **修复**：公共 `result_contract` 将 Registry 声明的所有 ViewSpec ID 登记到 workspace；Domain Registry 仍是面板身份唯一来源，未增加 GIS 特判。
- **验证**：修复前最小契约稳定失败，修复后通过；M302/答案/Composite **26/26**、生产 HTTP/异步/artifact/restart、compileall、architecture strict、Service smoke 和 Node projection smoke 均通过。
- **预防**：每个公共 View fallback 都必须同时校验 workspace 声明；新增结果类型优先提供 ViewSpec，不在 transport 或前端补面板名称。

## M303 异步 Composite 初始快照被误判为失败

- **现象**：真实 Docker Composite 的后台 worker 和 GIS/Economic Domain 执行实际能够完成，但验收脚本在轮询初始 `PLANNING` 快照时提前得到 `FAILED`，没有等待到最终结果。
- **根因**：Composite 运行尚未形成嵌套结果时，`get_run()` 复用了通用失败 fallback；异步轮询又把这个投影当作终态，掩盖了真实的 `PLANNING`/`EXECUTING` 状态。
- **修复**：活动 Composite 快照现在投影为 `PLANNING`/`EXECUTING`，结果保持有界的 pending 表达；验收优先使用 `get_observability()` 判断终态，再读取最终运行详情。没有修改执行授权或通过放宽判断来制造成功。
- **验证**：Docker M303 契约与相邻 Composite 回归 **12/12**；真实生产 HTTP、异步、artifact 和重启链路通过。
- **预防**：异步读取必须区分活动快照、终态快照和终态证据；不能把“结果尚未形成”投影成失败，也不能只用详情接口代替可观测状态。

## M303 真实模型 Composite 验收在中转链路超时

- **现象**：阶段唯一一次真实模型 Composite Planner 验收在 60 秒 harness deadline 内超时，`max_retries=0`，没有形成组件计划，也没有创建 execution run。
- **根因分类**：请求已经进入真实中转/模型调用边界，但 provider 响应未在有界时间内返回；这是 provider/网络延迟平面问题，不是 GIS 数据执行失败，也不是 Agent 生命周期失效。
- **处理**：保留 `FAILED`、`error_plane=harness`、deadline 和 `execution_run_created=false` 的脱敏 receipt；不增加无界重试、不放宽 schema、不把超时伪装成澄清或成功。
- **预防**：live 验收只在阶段门禁通过后显式执行一次；应单独显示“等待模型规划”的可恢复状态，并将 provider timeout 与事实澄清、计划拒绝、执行失败分开统计。

## M304 provider receipt 与前端阶段状态不一致

- **现象**：provider 规划失败已经带有 `failure.v1`，但前端阶段投影只看到 planner evidence，可能把“生成计划”显示为已完成；LLM 适配器包装异常时也可能丢失稳定错误码和可重试性。
- **根因**：失败 evidence 与阶段模型是两个投影入口；Composite Planner 只保留统一错误码，没有从底层异常安全提取有界 metadata。
- **修复**：新增领域中立 `provider-runtime.v1`，统一 health/deadline/structured-output receipt；仅透传有界 `code/retryable`，不透传异常文本。Console projection 将 provider/planning failure 的计划阶段标为不可用，并显示“模型暂时不可用/稍后重试”。
- **验证**：重建 Docker 后 M304/M300/M303 **24/24**，Node projection、compileall、architecture strict、Service smoke、生产 acceptance 和 readiness **200** 通过；唯一 live 为 60 秒、0 重试 timeout，未创建 run。
- **预防**：状态、failure、provider receipt 和 next action 必须从同一结构化 evidence 派生；新增 provider 字段必须经过安全白名单和幂等投影，不能把模型原文、prompt、URL 或密钥带入 Result/View/Artifact。

## M305 provider attempt 与可执行计划缺少统一边界

- **现象**：provider 规划已经能够返回结构化结果，但仅凭 planner 状态或 binding 指纹无法同时说明请求预算是否超限、是否发生 repair，以及计划是否真正通过 TaskPlan/DAG、ToolRegistry、workflow 和 execution binding。
- **根因**：provider deadline、阶段 Envelope、repair lineage 和执行 binding 原先分散在不同 evidence 字段；replay/fake client 没有 provider `metrics()` 时，阶段 Envelope 的预算统计也会丢失。
- **修复**：新增领域中立 `spatial-agent.planner-attempt.v1`，记录阶段、状态、结果类别、attempt/retry、Envelope 字节数、输出/期限预算、repair 和统一动作 ID；新增 `spatial-agent.canonical-plan-receipt.v1`，只有 accepted TaskPlan bridge 与 validated execution binding 同时成立才标记 `executable`。异步安全证据、Composite View、artifact 和 Console 复用同一白名单投影。
- **验证**：Docker 重建后 M304/M305 精简契约 **14/14**、M303/M283 跨入口回归 **16/16**，阶段合并回归 **30/30**；compileall、architecture strict、Service smoke、生产 acceptance 和 readiness **200** 通过。一次显式真实模型使用 60 秒、0 重试形成合法单组件计划并完成 sync/async 对照。
- **预防**：planner 的“已生成”与“可执行”必须分开表达；所有预算、动作和 repair 字段必须通过公共 receipt，不能在 HTTP、前端或 Domain 中自行猜测，也不能用 replay 成功替代真实 provider 成功率。

## M306 组件图校验与 TaskPlan 物化边界可能漂移

- **现象**：组件图在 Planner 规范化阶段已经校验，但如果后续调用方直接把原始组件列表交给 TaskPlan bridge，仍可能绕过前一层的依赖顺序、输入引用或布尔字段检查。
- **根因**：规范化和 TaskPlan 物化是两个可独立调用的公共 seam，前者的成功不能自动证明后者收到的对象没有被替换或变形。
- **修复**：`CompositeTaskPlanBridge` 在物化前重新调用公共组件图校验；组件身份、依赖存在性与先后顺序、typed input、required 类型和 data-kind 约束均 fail closed，不创建第二套执行授权。
- **验证**：Docker M306 组合契约、M303 canonical TaskPlan/binding 回归通过；非法后置依赖在 bridge 边界被拒绝。
- **预防**：任何从结构化计划到可执行对象的 bridge 都必须在自身边界重新验证关键 identity；不能仅依赖上游 fingerprint 或“已规范化”标记。

## M308-A Composite 嵌套答案未进入公共事实投影

- **现象**：子结果把用户答案放在嵌套 `result.answer` 时，Composite 组件投影只读取外层答案或 `summary`，导致前端的关键发现为空，答案上下文也拿不到该事实。
- **根因**：子运行 envelope 与嵌套 Result 都是既有合法形态，但 `_project_component` 没有覆盖嵌套 Result 的 `answer` 字段。
- **修复**：公共 Composite contract 按“外层 answer → 嵌套 summary → 嵌套 answer”顺序投影，答案和前端继续消费同一结构化事实；未增加领域专用分支。
- **验证**：Docker M308-A 定向契约 **4/4** 通过；覆盖 3+ 组件、混合数据形态、可选组件失败和答案上下文边界。
- **预防**：新增结果类型或 envelope 形态时，必须同时覆盖外层与嵌套 Result 的事实投影；不要只验证状态和 data profile。

## M308-A Docker 镜像未包含最新工作区测试

- **现象**：直接运行 Docker 定向测试时，容器报告找不到新测试模块。
- **根因**：工作区新增文件尚未进入本地镜像；容器运行的是旧构建内容。
- **处理**：先重建 `spatial-agent` 镜像，再执行同一条定向契约；代码与测试均在重建镜像中验证。
- **预防**：阶段新增测试或生产代码后，Docker 验收必须显式重建镜像；不要采纳旧容器对新文件的失败结果。

## M308 组件 workflow 约束与 handoff 合并发生语义漂移

- **现象**：Composite 未声明 workflow 时错误复用上下文约束，目录能力出现 `unknown constraints`；修复后 handoff 又把所有上下文约束无条件合并到 capability-specific workflow，导致 discovery workflow 被错误拒绝。
- **根因**：上下文级 workflow 约束、能力级 workflow 约束和组件 handoff 的适用范围没有在合并边界明确区分；把“可观察的上下文信息”误当成了“当前能力的执行授权约束”。
- **修复**：只有组件显式声明并通过匹配的 workflow 约束才进入该组件的执行校验；未声明时不继承不适用的上下文约束，handoff 仅保留与目标能力一致的有界事实，不改变 canonical TaskPlan、ToolRegistry 或 execution binding 门禁。
- **验证**：Docker M308 真实 GIS/Economic/Indicators 三组件组合与相邻 Composite 回归通过；discovery、组件执行和跨入口 View/Evidence identity 均保持一致。
- **预防**：新增上下文或 handoff 字段时，必须注明其生命周期阶段和适用对象；合并器要区分“事实/提示”和“执行约束”，并覆盖未声明、能力专属、跨组件依赖三种契约，不得无条件拼接约束列表。

## M308 跨入口 artifact 比较器混用不同层级状态

- **现象**：阶段验收初版把嵌套组件状态、Composite 运行状态和 artifact 公共 View 混在同一个比较层级，可能将合法的层级差异误报为跨入口不一致。
- **根因**：artifact/restart 验收没有先固定公共比较对象；内部运行快照与用户可见 View/Evidence 的职责边界被测试代码隐式混合。
- **修复**：跨入口验收统一比较公共 View、Evidence 和结果事实 identity；组件内部状态只作为独立的执行完整性断言，不参与 artifact View 的直接等值比较。
- **验证**：`scripts/m308_cross_entry_acceptance.py` 在 Docker 中确认 sync/async/HTTP/artifact/SQLite restart 的公共 View/Evidence identity 一致。
- **预防**：每个跨入口测试先声明比较层级（内部生命周期、Result、View、Evidence 或 Artifact），禁止用不同层级对象直接比较；新增投影时必须同时覆盖首次返回与恢复读取。

## M309 无 metrics 的 LLM 客户端导致 planner-attempt 假显示未调用

- **现象**：合法的 LLM 客户端只实现 `complete_json()` 而不提供可选 `metrics()` 时，规划已返回澄清或拒绝，但 planner-attempt receipt 可能显示 `not_started`、0 次尝试，且 provider 异常的 retryable 动作丢失。
- **根因**：Composite Planner 原先只合并客户端 metrics 和 envelope 大小；调用状态没有由 Planner 适配器提供最小兜底，异常恢复标志也没有经过安全边界。
- **修复**：LLM Planner 在调用前、成功和异常路径维护有界 `status/attempts/retries`；仅在异常提供布尔 `retryable` 时透传该字段，客户端已有 metrics 保持权威；不透传异常文本、URL、响应体或任意字段。
- **验证**：Docker M309-A 精简契约 **4/4** 通过，覆盖最小客户端成功、provider failure、语义拒绝和非法输出。
- **预防**：可选观测接口不能成为生命周期状态的唯一来源；所有 provider adapter 至少要在自身边界记录一次调用的开始/结果，并对公开 evidence 使用白名单投影。

## M309 结构化 answer 在聊天摘要中退化为对象字符串

- **现象**：某些结果返回结构化 `answer` 对象而不是旧版字符串时，聊天消息摘要直接把对象交给 DOM 文本，用户看到 `[object Object]`，或者看到不适合用户的内部字段。
- **根因**：聊天摘要兼容逻辑只优先读取 Composite View，随后把任意 truthy 的 `data.answer` 当作字符串，没有复用结构化答案的安全字段投影。
- **修复**：摘要只接受结构化答案中的 `summary/headline` 或明确字符串；其它对象不直接字符串化，继续回退到错误/状态文本。失败卡片也按 provider、planning/rejected、execution 等公共错误平面使用通用中文提示。
- **验证**：前端构建会在 Docker 镜像阶段执行；阶段收口保留 Node projection smoke 和浏览器/静态脚本解析门禁。
- **预防**：任何前端摘要入口都必须先经过公共 Result/View/Answer projection；禁止直接渲染未知对象或根据领域/工具名猜测用户文案。

## M310 前端 planning failure 阶段投影条件和字段命名不一致

- **现象**：后端已经返回 `planning_failure` 时，前端结果投影的失败卡片可以显示，但
  阶段条可能仍把“信息确认”或“生成计划”显示为等待，无法准确反映“等待补充、计划
  未生成、计划校验未通过”。
- **根因**：归一化结果使用公开字段 `planning_failure`，`buildPhases` 的内部参数使用
  `planningFailure`；中断补丁还遗漏了一个逻辑或运算符，导致阶段判断既不完整又可能
  触发语法错误。
- **修复**：在单一前端 projection 内统一使用受控的 planning-failure 对象，按状态映射
  阶段和中文文案；补齐逻辑运算符，并对白名单状态、下一步提示和内部错误码做有界投影。
- **验证**：Node projection smoke 和 Docker 内 projection smoke 均通过，覆盖 clarification、
  preview invalid/failed、binding failed、rejected 与 provider failure；内部错误码不会
  出现在用户 HTML 中。
- **预防**：新增结构化字段时同时检查“公开字段名、内部参数名、阶段判断和渲染入口”；
  前端 smoke 至少覆盖成功、澄清和每个用户可见失败平面。

## M310 真实模型返回结构化澄清而未进入执行

- **现象**：本阶段唯一一次真实模型验收已到达 provider，structured output 通道成功，
  但模型认为请求仍缺少可确定的事实，返回 `NEEDS_CLARIFICATION`，未创建执行任务。
- **处理**：按真实语义澄清记录，不将 provider 通道成功误报为分析执行成功；Replay 仅
  用于离线验证已注册能力和真实 GIS 数据链路，不替代 live 结果。
- **预防**：真实模型验收必须同时记录 provider 通道状态、语义状态和 run 创建边界，
  并通过公开的 Result/View/Evidence 契约展示下一步；不得保存模型原文、prompt 或密钥。
## M310：Domain workflow resolver 失败时不能回退旧 context workflow

### 问题

Composite Planner 选中 capability 后，TaskPlan bridge 需要通过 Domain 的
resolver 得到该 capability 对应的 workflow。旧逻辑在 resolver 不存在、返回空值
或调用失败时，可能继续使用 request context 中的 workflow 快照。这样会把 discovery
阶段的历史/建议信息误当成 Domain 对当前 capability 的执行授权，造成 capability、
workflow 和 TaskPlan 身份不闭合；某些场景还会错误进入 preview。

### 根因

context workflow 是有界的发现证据，不是执行授权。bridge 同时承担了兼容旧 Domain
接口和物化 TaskPlan 的职责，原先把 fallback workflow 用作 resolver 失败后的兼容
路径，缺少“选中 capability 必须由 Domain 再确认 workflow”的门禁。

### 修复

- 选中 capability 且未提供显式 replay workflow 时，必须调用 Domain resolver；resolver
  不存在、返回空 workflow 或 workflow 身份不完整时，返回
  `capability_workflow_unresolved`。
- resolver 返回的 workflow 必须与 capability 声明的 `workflow_ids` 一致；不一致时
  返回 `capability_workflow_mismatch`，并在 preview 前终止。
- context workflow 仍可作为候选和约束提示，但不能替代 Domain-owned resolver。
- 增加单组件、不可用、未绑定、resolver 失败和 workflow mismatch 的精简契约，确认
  不创建未验证的执行任务。

### 预防

以后新增 capability/workflow 映射时，必须同时覆盖 capability catalog、Domain
resolver、workflow index、TaskPlan bridge 和 execution binding 的身份对照；测试中
要加入“context 有 workflow 但 resolver 失败”的反例，防止发现证据重新变成授权。

## M311 前端数组证据误用对象选择器

### 现象

后端已经在 planner evidence 中输出 `analysis_intents` 数组，但前端归一化后数组为空，
因此用户看不到本次分析包含的查询、趋势或空间关系等通用分析内容。

### 根因

前端已有的 `firstRecord()` 只接受对象，用它读取数组证据时会安全地回退为空值。对象和
数组证据没有分别使用匹配的选择器。

### 修复

- 增加数组专用的有界选择器，按优先级读取首个非空 `analysis_intents`。
- Composite View、异步/artifact evidence 和 Console projection 均只保留经过
  `analysis-intent.v1` 归一化的字段。
- 前端用通用的“本次分析内容”展示操作和结果类型，不按 GIS、经济或工具名写页面分支。

### 预防

新增结构化证据字段时，先确认字段形态（对象、数组或标量），不要复用形态不匹配的
选择器；至少覆盖后端 View、异步持久化和前端 projection 三个边界。

## M311 Docker HTTP 验收容器误用 127.0.0.1

### 现象

在宿主机服务已启动且健康检查为 200 的情况下，从 Docker 验收容器运行真实本地 GIS
HTTP 脚本时出现 transport failure。

### 根因

验收脚本运行在独立容器内，`127.0.0.1` 指向验收容器自身，而不是宿主机上的服务；这
不是 GIS 后端或 HTTP 业务链路失败。

### 修复与预防

Docker Desktop 环境从容器访问宿主机服务使用 `host.docker.internal`，并先检查宿主机
服务 `/health/ready` 为 200，再执行 HTTP/artifact/异步对照。脚本输出只保留脱敏状态，
不记录密钥、prompt 或模型原文。

## M311 LLM 工具计划缺少结果类型导致 unknown Result

### 现象

一次真实模型调用中，模型选择的栅格元数据步骤实际执行成功，但由于计划省略
`output.type`，顶层 Result 被标成 `unknown`，前端出现不可用的 generic 视图。

### 根因

旧 `task_plan_schema` 和 LLM Planner 边界允许带工具步骤的计划没有公共结果类型；运行时
无法安全地从工具名称猜测 Result Contract，只能把结果归为 `unknown`。

### 修复

- 计划 schema 要求顶层 `output` 且要求 `output.type`。
- 正常 provider 计划在进入执行前检查结果类型，缺失时以规划失败结束，不创建“看似成功
  但类型未知”的结果。
- 保留历史单工具快捷路径兼容；不通过工具名硬编码推断领域结果类型。

### 预防

任何新增 Planner、Result 或 View 入口都要验证 `计划输出类型 → Result Contract →
View/Artifact` 的完整传播；不能只断言步骤执行成功而忽略结果类型和视图可用性。

## M312 Composite provider failure 被末尾投影覆盖

### 现象

M304 provider failure 契约期望保留底层 `provider_timeout` 和 `retryable=true`，实际结果
却被改写为 `planner_provider_failed`，导致前端和恢复动作丢失更准确的 provider 分类。

### 根因

`CompositePlanningApplication` 先按 `details.provider_failure` 构造了安全的 provider
failure evidence，随后异常处理末尾又无条件写入通用 planning failure，覆盖了前面的结果。

### 修复与预防

- provider failure 分支只保留底层安全错误码、分类和 retryable；通用 failure 只用于非
  provider 异常。
- 回归测试覆盖“底层 provider code 与规划器包装 code 不同”的场景，并检查下一步动作。
- 同一异常处理函数中不得对同一个公共 evidence 字段进行无条件二次写入；新增错误投影
  后应运行对应的最小 failure contract。

## M312 Docker Compose 环境文件与数据卷不一致

### 现象

容器环境变量显示真实数据根目录，但容器内只有项目 `data` 目录中的 Economic 文件，
GIS 数据不可用；健康检查仍可能返回 200，容易误判为 GIS 数据已经挂载。

### 根因

Compose 的变量插值发生在 `env_file` 生效之前。执行 `docker compose` 时未显式传入
`--env-file .env.production`，卷路径从默认 `.env` 插值为 `./data`；服务环境变量则仍从
`.env.production` 读取，形成配置与挂载分离。

### 修复与预防

- 生产/真实 GIS 验收统一使用：
  `docker compose -f docker-compose.prod.yml --env-file .env.production ...`。
- 重建后同时检查 `docker compose config` 的卷源、容器 `/data` 文件清单和数据健康报告，
  不能只检查 `/health/ready`。
- 健康检查应区分“依赖库可用”和“配置数据可读”；缺失数据必须进入结构化 degraded/
  unavailable 证据。

## M312 Live 验收轮询预算小于 provider 预算

### 现象

真实模型请求已提交并最终完成，但验收脚本提前报告“异步 run 未进入终态”。

### 根因

本次手动参数将轮询次数与间隔组合成约 18 秒，小于 provider 允许的约 90 秒预算；服务端
worker 仍在正常执行，harness 的失败不是业务 run 失败。

### 修复与预防

- live 验收的轮询总预算必须大于 `request_timeout + 异步排队余量`，默认使用脚本的有界
  轮询配置，不手动缩短到低于 provider deadline。
- harness 失败时先查询已有 run 的 observability 和 artifact，再决定是 provider、harness
  还是执行失败；不要因为轮询超时重复发起模型请求。
- 复核已有 run 使用 `--verify-run-id`，只做无模型合同检查。

## M312 直接执行验收脚本缺少项目根路径

### 现象

`python scripts/m308_real_composition_acceptance.py` 直接执行时报 `ModuleNotFoundError`，
但作为模块或其它入口运行正常。

### 根因

脚本导入 `agent` 前没有把仓库根目录加入 `sys.path`；脚本工作目录不是可靠的模块导入前提。

### 修复与预防

- 直接执行的仓库验收脚本在导入项目包前根据 `__file__` 注入仓库根路径。
- 每个新验收脚本至少做一次“从仓库根目录直接执行”的 smoke；错误只记录类型和状态，
  不输出配置密钥或模型原文。

## M312 前端健康浏览器 smoke 依赖 Chrome CDP

### 现象

`console_health_smoke.js` 在未启动 Chrome CDP `9222` 时失败，错误为连接被拒绝；这不
代表页面、Node projection 或后端服务失败。

### 处理与预防

- 将 Node projection smoke 与需要浏览器 CDP 的交互 smoke 分开报告。
- 浏览器 smoke 执行前显式启动隔离 Chrome/CDP，并先检查 `/json/list`；若环境未提供 CDP，
  记录为环境未满足，不伪装成项目通过。

## 2026-08-27 经济指标泛称测试触发澄清

### 现象

在前端提问“查询洪山区 2025 年经济指标”时，回答为 `planner needs clarification`，没有直接返回经济数据。

### 诊断

- “经济指标”没有指定具体指标，Economic Domain 的 `indicator` 是必填事实；显式选择 Economic 后，系统实际只缺少 `indicator`，进入澄清属于预期行为。
- 前端默认领域仍为 GIS；如果继续使用已绑定 GIS 的会话，请求会沿用 GIS 领域，而不会自动切换到 Economic。
- 新的自动路由会话对泛称“经济指标”的匹配词不够宽，可能在领域选择阶段返回 `no_domain_capability_match`。
- `agent/llm_planner.py` 在模型返回 `needs_clarification` 但缺少 `message` 时使用英文兜底文案 `planner needs clarification`，应由后续用户体验任务改为结构化中文澄清。

### 当前验证

- 使用新会话、自动路由和规则 Planner 提交该问题：未匹配领域。
- 使用显式 Economic 领域提交该问题：返回 `NEEDS_CLARIFICATION`，缺少字段为 `indicator`。
- 使用新会话提交“查询洪山区 2025 年 GDP”：Economic 自动路由和本地真实数据执行完成。

### 测试约定与预防

- 测试经济查询时，先选择“区域经济分析”或“智能选择”，并新建会话。
- 查询具体指标时使用“查询洪山区 2025 年 GDP”，不要只写“经济指标”。
- 测试“经济指标”泛称时，应验证系统给出中文结构化澄清，并提供可查询指标目录，而不是把澄清误判为数据源故障。

## 2026-08-27 Economic 异步执行的 runtime context 指纹不一致

### 现象

选择“区域经济分析”后提交 Economic 请求，前端返回 `persisted runtime context differs from the current runtime`，任务没有进入工具执行。

### 根因

- 异步提交阶段通过 `build_runtime_context_snapshot()` 读取 Economic Domain 的 `tool_provider_info()`，工具提供方 ID 为 `economic-source-bound`。
- worker 执行阶段通过 `ToolRegistry.provider_info()` 读取实际 provider，ID 为 `native`。
- 两个上下文虽然领域、规划器、后端和工具数量相同，但 provider identity 不同，指纹自然不同，`assert_runtime_context_compatible()` 按设计拒绝执行。
- 前端绑定领域后的请求会自动转为异步入口，因此该问题在前端稳定暴露；清空会话或重新选择同一领域不能修复。

### 处理原则

- 统一 Domain 声明的 provider identity 与实际 `ToolRegistry` provider identity，并保留 runtime context 一致性门禁。
- 增加 Economic 异步提交到 worker 的 context fingerprint 回归；不得通过跳过校验或接受任意 provider identity 规避问题。
- 阶段收口时同时验证同步、异步、SQLite/restart 和前端入口。

### 本次修复

- `NativeToolProvider` 现在默认从 adapter 读取稳定的 `provider_id`；未声明时仍兼容使用 `native`。
- Economic、Indicators、Text 的提交快照与实际 Registry provider 现在使用同一 identity。
- 新增内置 Domain context 一致性回归和 Economic 异步执行回归。
- Docker HTTP 异步入口已验证返回 `COMPLETED`；M135 runtime-context 回归 **12/12** 通过。

## 2026-08-27 Goal 长文本附件化与恢复读取过量

### 现象

长 Goal 粘贴后，Goal 工具显示为 `pasted text file: ...` 的附件路径；恢复时又容易
重复读取完整恢复卡、历史账本、全量源码和测试，挤占实际代码修改的上下文预算。

### 根因

- 平台会将较长的多行粘贴内容保存为临时附件，Goal objective 记录的是附件引用，
  而不是原文文本。
- 项目原先虽然约定了快照和任务账本，但账本中的当前任务记录追加在历史区末尾，
  恢复脚本无法可靠地按“当前/最近”边界截取。
- `tasks/task-state.md` 与历史恢复文档仍被部分流程误认为默认入口。

### 处理

- 明确 `docs/agent-work-state.md` 为唯一默认交接文档；顶部固定记录当前阶段、完整
  进行中任务、Spec/Plan、明确文件、验证、阻塞、未提交变更和下一步。
- `tasks/task-progress.md` 顶部固定“当前进行中”和“最近完成”两个有界区块，旧记录
  归入历史区；恢复脚本只读取这两个区块，不再要求读取详细状态账本。
- 恢复顺序固定为：工作快照 → 任务账本当前/最近区块 → 当前任务明确文件；其它历史和
  源码仅在证明为直接依赖时按主题读取。
- Goal 文本的持久化依据同步写入仓库总体方向文档，不依赖临时附件长期保存项目规则。

### 预防

- 每个子任务开始、完成或暂停后立即更新交接快照和任务账本。
- 代码实现优先；测试按独立风险集中执行，不按任务数量重复运行；简单文档或样式修改
  可不运行测试，Runtime、HTTP、持久化、恢复和真实模型边界仍保留针对性验收。

## 2026-08-27 子代理并行开发遇到 provider 429

### 现象

并行启动 backend 和 frontend 子代理执行 M313 答案流/实时事件最小收口时，两个子代理
均未返回代码，平台通知为 `429 Too Many Requests`，并在达到重试上限后结束。

### 判断

- 失败发生在子代理 provider 调度层，尚未进入项目代码执行；不能把它归因于 Runtime、
  RunEvent、前端事件消费者或测试代码。
- 之前的短协作试运行已证明角色规约、任务卡、完成通知和同一 `agent_id` 续接可用；
  本次暴露的是并发 provider 配额/限流风险。

### 处理原则

- 历史处理曾建议保持总并发度不超过 3；当前已收敛为单 Agent、最大并发度 1，不再启动并行子代理，避免 provider 限流和共享工作树冲突。
- 关闭失败会话并将任务标记为可恢复受阻；由主控在不扩大范围的前提下继续关键路径。
- 后续阶段记录子代理 provider 状态，但不保存 request id、密钥、Prompt 或模型原文；
  真实模型调用继续由主控在阶段收口时显式执行。

## 2026-08-27 M313 实时验收中的事件、镜像与浏览器夹具问题

### 现象

- 前端事件消费者遇到 HTTP 500 时立即结束轮询，未执行有限重试。
- Docker 增量验收复用了旧镜像，导致容器缺少本轮新增的答案流测试；浏览器验收脚本还硬编码了旧版 `spatial_analysis_result` 与 `raster/composite/map` 面板。
- 真实模型请求在验收脚本的 60 秒窗口内仍处于规划阶段，脚本超时退出，但服务端随后完成了该 run。

### 根因

- 轮询实现把所有非 2xx 响应当作立即不可用，没有区分临时错误与明确不支持。
- Docker `run` 不会因为源码变化自动更新已构建镜像；浏览器夹具没有跟随动态 Result/View 契约迁移。
- Provider 延迟超过 harness 的观察窗口；超时只代表验收窗口结束，不能推断服务端 run 已失败。

### 处理与预防

- 对 408、425、429 和 5xx 执行最多三次指数退避；404、405、501 等明确不支持立即回退或结束。
- 代码或新增测试进入 Docker 验收前显式重建镜像；阶段浏览器夹具只断言动态结果类型、`map` 视图、轨迹和错误状态，不固化某一领域的面板集合。
- 真实模型阶段只调用一次；超时后读取已有 run 状态和事件，不重复提交。只记录脱敏状态、事件数量和 streaming 标志，不保存密钥、Prompt 或模型原文。

### 当前验证

- Docker M313 事件/答案流契约 **11/11**、Node event smoke、生产验收、Domain SSE/Last-Event-ID、服务重启恢复、浏览器动态结果和 compileall/architecture strict 均通过。

## 2026-08-28 M314 SSE 跨分页终态与真实回答验收

### 现象

- 某个已完成 Run 的 SSE 请求使用 `limit=100` 时只返回前 100 个事件，连接提前结束；最后看到的是 `answer_delta`，没有看到终态事件。
- 真实模型更换配置后的首次请求曾返回 HTTP 401/404；更新为可用配置后，Provider 探测和真实 GIS 回答均成功。

### 根因

- HTTP 读取结果中的 `terminal=true` 表示整个 Run 已进入终态，不表示当前分页已经包含 `run_completed` 或 `run_failed` 事件。生产 FastAPI 和 stdlib 入口都错误地直接使用该字段关闭流。
- 401/404 属于 Provider 配置或认证边界，不是 GIS、SSE 或 Runtime 执行错误；必须按安全错误 receipt 停止无效重试。

### 处理

- 在 `agent/run_events.py` 增加 `page_contains_terminal_event()`，两个 HTTP 传输入口只有在当前页确实包含终态事件时才关闭；若 Run 已终态但当前页仍有更多事件，则沿 `next_cursor` 继续读取。
- 增加 100+ 事件最小回归，先确认红灯再修复；保留轮询、Last-Event-ID 和恢复语义。
- 分离规划与答案模型预算：答案默认 20 秒、768 token、0 重试，可通过 `OPENAI_ANSWER_TIMEOUT_SECONDS`、`OPENAI_ANSWER_MAX_OUTPUT_TOKENS`、`OPENAI_ANSWER_MAX_RETRIES` 覆盖，减少回答阶段无效等待和 token 消耗。

### 当前验证

- Docker 真实 Provider 探测：`READY`，约 928 ms，1 次请求、0 重试。
- Docker 真实 DeepSeek + 本地 GIS：`COMPLETED`，1 次规划、0 重试，结果与 artifact/evidence/polling 对照通过。
- 成功 Run SSE：384 个事件，其中 368 个 `answer_delta`、1 个终态事件；`Last-Event-ID: 1` 续传完整到第 384 个事件。
- Docker M16/M313/M313-answer 定向回归 **26/26**、compileall、architecture strict、前端答案流 smoke 通过；不保存密钥、Prompt、模型原文或隐藏思维链。

## 2026-08-28 真实 DEM 说明请求的 Planner JSON 截断

### 现象

- 前端请求“查询洪山区 DEM 栅格元数据，并用通俗中文说明覆盖范围、分辨率、坐标系、高程最小值和最大值，最后给出简短结论”时，显示 `规划错误 / invalid_model_response / 不可重试`。
- 同一请求的失败 Run 使用 `completion_tokens=2048`，与当前 Planner 输出上限完全相等。

### 根因

- DeepSeek 的 OpenAI 兼容 `json_object` 响应在本次请求中生成超过 2048 token，返回内容在 JSON 完成前被截断；应用层随后正确拒绝不完整 JSON。
- 原有 Runtime 只把该错误投影为不可重试失败，没有给 Provider 一次低成本、明确约束的计划恢复机会。

### 处理

- Planner 对 `invalid_model_response` 仅执行一次紧凑计划恢复：只要求最小执行计划，不生成回答、解释或 Markdown，并限制步骤/字段规模。
- 恢复结果仍经过既有 TaskPlan、工具注册、workflow、执行绑定和结果契约校验；认证、超时、拒绝和工具错误不走该恢复。
- TaskPlan schema 增加有界数组/字符串约束；Provider metrics 记录脱敏 `finish_reason`，Planner metrics 记录 `compact_recovery_attempts`。

### 当前验证

- 原始真实请求在 Docker + DeepSeek + 本地 GIS 下已返回 `COMPLETED`，规划选择 metadata/statistics 两步，答案生成 `streaming=true`。
- 真实复验只发生一次有界恢复，没有自动 provider retry；不保存 key、Prompt、模型原文或隐藏思维链。

## 2026-08-28 DeepSeek 官方接口的结构化规划兼容与输出预算问题

### 现象

- `OPENAI_BASE_URL=https://api.deepseek.com` 与 `chat_completions` 路径可达，但真实
  GIS 规划请求不能稳定完成。
- `json_schema` 模式被接口快速返回 HTTP 400；切换 `json_object` 后，输出上限 4096
  时模型输出被截断为非法 JSON，输出上限 10000 时复杂规划又超过交互等待预算。

### 判断

- 官方 DeepSeek OpenAI 兼容入口的基础地址是 `https://api.deepseek.com`，项目会自动
  拼接 `/chat/completions`；这不是 URL 拼接错误。
- 简单 Provider 探测可以成功，说明不是单纯网络不可达；故障集中在真实规划请求的
  结构化协议兼容性和过大输出预算，不是 GDAL/GIS 执行错误。

### 处理

- 本地生产配置使用 `OPENAI_STRUCTURED_OUTPUT_MODE=json_object`，应用层继续执行完整
  JSON、能力、TaskPlan、ToolRegistry、执行绑定和结果契约校验。
- Planner 提示要求立即返回紧凑 JSON，不返回解释、Markdown 或分析文本。
- `OPENAI_TIMEOUT_SECONDS` 设为 45，`OPENAI_MAX_RETRIES` 设为 1；真实请求验证后将
  `OPENAI_MAX_OUTPUT_TOKENS` 收敛为 2048，避免模型在大预算下长时间生成。
- 不把 Provider 原始响应、密钥或 Prompt 写入报告、artifact 或问题日志。

### 当前验证

- 临时 2048 输出上限、0 重试下，同一真实洪山区 DEM 请求成功完成，规划耗时约 7.1 秒。
- 生产配置重载与完整 HTTP/SSE/答案流验收仍在进行；若 Provider 再次超时，按失败
  receipt 停止重复调用，不伪造成功。

## 2026-08-28 Planner 紧凑恢复仍受原始 token 上限影响

### 现象

- 前端同一 DEM 栅格元数据说明请求再次返回 `invalid_model_response`。
- 失败 Run 的主 Planner 请求和紧凑恢复请求都以 `finish_reason=length` 结束，且
  completion 都达到 2048；说明上一次恢复实际上没有增加可用输出空间。

### 根因与处理

- 原有 `LLMPlanner` 虽然只恢复一次，但调用的是原始 `complete_json`，因此继续复用
  Planner 的 2048 上限。
- `OpenAIPlannerClient` 新增独立 `complete_compact_json`：恢复预算限制在 4096～8192，
  并设置 `temperature=0`；主 Planner 预算、ToolRegistry、TaskPlan 和执行门禁不变。
- 不支持该扩展方法的 fake/replay client 继续走原有两参数接口，避免破坏离线测试 seam。

### 当前验证

- Docker M16 定向回归 **17/17** 通过。
- 同一会话真实 DeepSeek + 本地 GIS 请求 `COMPLETED`，`compact_recovery_attempts=1`，
  恢复 completion 为 1183，答案已形成；未保存 key、Prompt、模型原文或完整异常。

## 2026-08-28 用户答案预算过小导致自然语言回答提前结束

### 现象

- DEM 栅格元数据请求能够完成，但对话答案只输出覆盖范围、分辨率和坐标系等前半段，
  高程最小值、最大值和简短结论没有出现，用户容易误以为模型没有完整回答。

### 根因与处理

- 答案生成使用独立配置，但默认答案预算被限制为 768 token；普通答案 schema、流式答案和
  前端回退又共同限制为 1800 字符。对推理型或需要逐项说明的模型，这一预算过于保守。
- 答案预算已独立提高到默认 4096 token，普通答案可见上限提高到 6000 字符；Planner 的
  结构化预算、工具参数校验和一次性截断恢复不变。显式 `OPENAI_ANSWER_MAX_OUTPUT_TOKENS`
  仍可用于针对具体 Provider 调低或调高预算。

### 当前验证

- Docker M16 + M313 答案流回归 **21/21** 通过，1 项真实模型测试按开关跳过；compileall
  和前端语法检查通过。
- 未重复调用真实模型；未保存 key、Prompt、模型原文或完整异常。
