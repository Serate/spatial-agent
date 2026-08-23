# Agent 开发问题记录（当前索引）

本文件用于记录近期仍有参考价值的工程问题，使用中文维护。每条问题至少包含：现象、根因、诊断、修复和预防。历史条目已归档到 `docs/archive/context-history/agent-development-issues-history.md`，恢复上下文时不得全文读取。

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
