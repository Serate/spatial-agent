# Agent 开发问题记录（当前索引）

本文件用于记录近期仍有参考价值的工程问题，使用中文维护。每条问题至少包含：现象、根因、诊断、修复和预防。历史条目已归档到 `docs/archive/context-history/agent-development-issues-history.md`，恢复上下文时不得全文读取。

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
