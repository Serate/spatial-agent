# Spec：M329 通用请求路由与跨域能力汇聚

## Objective

解决普通问题被默认绑定到 GIS/Composite Planner 的问题。用户可以提交任意领域问题；模型在受控能力目录中自主选择直接回答、工具行动、白名单 Web 搜索、工具提案或澄清。没有可用数据时，Runtime 必须保留已知事实并返回清晰的降级说明。

## Public contract

新增 `spatial-agent.request-mode.v1`，字段为 `mode`、`reason_code`、`tool_count`、`execution_started`。模式由 Runtime 根据实际行动推导，不增加分类模型调用。该字段进入 Result、SQLite、Artifact、execution record、终态事件和 HTTP 投影。

通用能力 Host 必须提供：

- 稳定的聚合 capability catalog 和工具定义；
- `provider_id`、健康状态、工具 owner 和按 owner dispatch；
- Domain preflight 转发和单个 provider 不可用时的局部 degraded 状态；
- 冲突工具名 fail closed，禁止静默重命名。

## Runtime behavior

- `/runs` 默认使用通用 Runtime；`/domains/{domain_id}/...` 继续使用明确 Domain Runtime。
- 通用 Runtime 默认使用真实模型 + local backend + full ReAct。
- 普通问题直接走 `finish` 并流式生成答案；需要事实时再调用注册工具或 Web。
- 工具失败、数据缺失、网络不可用和模型不可用都必须通过统一 Result/Evidence 表达，不能伪造结论。
- Tool proposal 仍遵循 sandbox + 人工审批 + 同一 Run 恢复。

## Commands

- 离线紧凑测试：`python -m unittest tests.test_m329_general_route -v`
- 编译检查：`python -m compileall -q agent domains`
- 架构检查：`python scripts/architecture_check.py --strict`
- Docker 服务与阶段验收：使用现有 `docker compose` 服务和显式 live acceptance 脚本。

## Testing strategy

只新增一个紧凑契约测试模块，集中覆盖模式投影、聚合 dispatch、直接回答、降级、入口隔离和恢复。阶段收口运行受影响回归、compileall、architecture/index、readiness 和一次真实模型 + Docker 验收；不把 live 或全量测试放入默认 CI。

## Boundaries

- Always：复用现有 Run/ReAct/ToolRegistry/Result/Evidence/Artifact/SSE 契约，所有 provider 失败可审计。
- Ask first：新增外部依赖、扩大 Web 白名单、改变工具提案上线策略或改变显式 Domain API。
- Never：绕过 schema/权限/审批、自动发布模型生成工具、伪造数据来源、保存隐藏思维链或敏感配置。

## Success criteria

1. 非 GIS 普通问题无需关键词即可得到模型回答。
2. 跨领域问题可以由模型组合已登记工具并生成自然语言总结。
3. 无工具或数据不可用时仍能给出边界清晰的回答或澄清。
4. 通用入口与显式 Domain 入口互不污染。
5. SQLite、Artifact、SSE、审批恢复和前端读取保持核心结果一致。
