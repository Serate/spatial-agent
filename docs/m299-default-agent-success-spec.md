# M299 默认 Agent 成功路径规格

## 目标

产品入口已经默认选择真实模型与本地数据，但默认 Agent 仍可能因上下文过大、候选信息过散、事实不足或数据未就绪而直接澄清。M299 要让这些状态可解释、可恢复，并让有充分事实的开放问题更容易进入现有 TaskPlan/execution binding 闭环。

## 范围

- `openai + local` 是产品入口缺省；显式选择和离线低层调用语义保持不变。
- Planner context 按能力索引、候选摘要、执行闭合信息分层投影，使用一个版本化字节预算。
- selection、clarification、discovery 和 provider structured-output evidence 在同步、异步、artifact/restart、HTTP 和前端之间保持核心 identity。
- 前端显示用户可理解的阶段与下一步，不显示内部推理。

## 不在范围内

- 不重写 Runtime、Planner、ToolRegistry、生命周期或领域适配器。
- 不增加固定区域、固定问句、专题专用分支或新的 RAG 数据源。
- 不通过放宽 schema、权限、数据就绪或 execution binding 来提高表面成功率。
- 不将真实 live 调用放入默认测试或 CI。

## 公共契约

1. `planner-envelope` 必须声明 schema version、总字节预算、投影层级和脱敏状态；超预算返回稳定 reason code。
2. `selection-evidence` 必须保留 request fingerprint、候选/选中能力的 domain/capability identity、data profile、workflow/readiness 摘要和澄清状态。
3. 选中能力仍需通过现有 capability → workflow → ToolRegistry → TaskPlan → execution binding 门禁。
4. `NEEDS_CLARIFICATION` 必须包含可读 message、缺失字段或不可用原因、next actions；不可创建 execution run。
5. 前端阶段投影必须区分至少 `discovering`、`understanding`、`planning`、`executing`、`summarizing` 及终态，并支持旧载荷安全降级。

## 命令与验证

- Docker build：`docker compose -f docker-compose.prod.yml up -d --build`
- Compact contract：在 Docker 中运行 M299 及相邻 Planner/Context/HTTP contract 一次。
- 静态门禁：Docker `compileall`、`architecture_check.py --strict`、Node projection smoke、生产 readiness。
- 显式验收：使用真实 Docker 数据运行一次 Replay/Rule 对照；若配置可用，再运行一次真实模型，不保存模型原文。

## 成功标准

- 默认产品请求未提供 planner/backend 时，能观察到 `openai + local`，并在阶段条中看到真实结构化阶段状态。
- 具有完整事实的开放问题可将必要候选交给 LLM Planner；上下文不会因层级预算不一致在本地提前拒绝。
- 信息不足、候选不明确、数据不可用和模型输出不合规分别返回稳定、可读、可恢复的结构化结果。
- 同一请求在同步/异步、HTTP、artifact/restart 中的 request/discovery/selection/binding 核心 identity 一致。
- 默认 compact/CI 保持离线、精简、可重复；live 只作为显式验收证据。

## 边界

- 始终：校验输入、限制上下文、过滤敏感字段、保留证据、运行阶段收口门禁。
- 需确认：新增依赖、修改 CI 触发策略、改变持久化 schema 或外部数据源。
- 禁止：提交密钥、保存模型原文、绕过工具/权限/数据门禁、删除失败测试来制造绿色结果。
