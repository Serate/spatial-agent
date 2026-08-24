# Agent 开发问题记录（当前索引）

本文件用于记录近期仍有参考价值的工程问题，使用中文维护。每条问题至少包含：现象、根因、诊断、修复和预防。历史条目已归档到 `docs/archive/context-history/agent-development-issues-history.md`，恢复上下文时不得全文读取。

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
