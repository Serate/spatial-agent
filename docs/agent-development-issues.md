# Agent 开发问题记录（当前索引）

本文件用于记录近期仍有参考价值的工程问题，使用中文维护。每条问题至少包含：现象、根因、诊断、修复和预防。历史条目已归档到 `docs/archive/context-history/agent-development-issues-history.md`，恢复上下文时不得全文读取。

## 恢复上下文载入过量

- **现象**：新对话按旧约定依次读取恢复档案、任务档案和完整问题日志，三份文件累计数十万字符，当前阶段和阻塞项被历史内容淹没。
- **根因**：历史文档长期追加，虽然文首写了“不要全文读取”，但文件路径本身仍会诱发全文加载；启动入口和历史档案没有物理分离。
- **诊断**：先检查文件大小和恢复脚本的默认路径，再确认当前短快照是否能独立说明目标、阶段、证据和下一步。
- **修复**：将 `docs/agent-context-current.md` 定为唯一状态源，`scripts/resume_context.ps1` 定为唯一恢复命令；启动命令默认只输出当前卡、Git 状态和最近提交，历史仅通过主题参数有界检索。
- **预防**：恢复默认历史文件数为 0；源码最多按需定位 2 个文件、测试最多 1 个文件；短快照超过约 3KB 时先压缩或轮换，不继续堆叠启动文档。`task-resume`、问题日志和 milestones 只按需读取。

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
