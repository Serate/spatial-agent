# Spec: M293 多组件事实协调与可恢复 Composite 续跑

## Objective

当 Planner 已选择多个已注册组件、但其中一个或多个组件缺少必要事实时，系统返回一次领域中立的结构化澄清。用户补充事实后，系统必须保留原请求指纹、组件集合、能力身份和 Planner selection fingerprint，重建公共 context，重新生成并校验 canonical TaskPlan/DAG，只有全部必需事实满足时才创建执行 run。

用户不应看到工具参数、模型原文或 continuation token 内容；用户只看到每个分析部分缺少什么、补充方式、当前计划状态和可读的下一步。

## Public contract

1. 新增版本化 `spatial-agent.composite-fact-handoff.v1`，包含有界 `components[]`；每个组件保留 `component_id`、`domain_id`、`capability_id`、requirements、known facts、workflow constraints、missing fields 和 state。
2. 多组件 continuation 绑定原始 request fingerprint、组件 ID/领域/能力集合、Planner selection fingerprint、允许的分组件字段白名单、schema version 和过期时间；签名载荷不得包含 prompt、模型原文、密钥、私有路径或完整原始数据。
3. 补充事实支持按 `component_id` 分组；未知组件、未知字段、错误类型、过期 token、请求指纹变化和组件集合变化均 fail closed。单组件 M292 continuation 保持兼容。
4. 补充后必须重新执行 `context → capability selection → Planner → completeness/repair → TaskPlan/DAG gate`；不得拼接旧计划或绕过 ToolRegistry。
5. 未完成多组件澄清不创建 execution run；成功续跑使用既有同步/异步、artifact、SQLite/restart 和 evidence 生命周期。
6. HTTP 与前端只投影安全的多组件缺失字段、补充状态、计划状态和 evidence；不把 token 传给用户界面或 Domain 私有实现。

## Commands

- 构建镜像：`docker compose -f docker-compose.prod.yml build spatial-agent`
- 启动验收服务：`docker compose -f docker-compose.prod.yml up -d --force-recreate spatial-agent`
- 阶段契约：`docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m293_multi_component_continuation -v`
- 统一门禁：`docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains evaluation production_api.py serve_api.py`
- 架构门禁：`docker exec ai-agent-spatial-agent-1 python scripts/architecture_check.py --strict`

## Project structure

- `agent/runtime_core/`：公共 handoff、continuation 和 TaskPlan gate。
- `agent/application/`：Composite prepare/submit 与 HTTP 语义透传。
- `agent/composite_view.py`、`web/src/console_result_projection.js`：领域中立结果投影。
- `tests/test_m293_multi_component_continuation.py`：单个 compact contract 模块，集中覆盖独立失败模式。
- `docs/`、`tasks/`：Spec、Plan、恢复快照、阶段记录和中文问题日志。

## Code style

继续使用小型、纯函数式 projection/normalizer 和显式 schema version；内部异常使用稳定 `code`，跨边界只返回有界结构化字段。例如：

```python
return {
    "schema_version": "spatial-agent.composite-fact-handoff.v1",
    "state": "required",
    "components": projected_components[:8],
    "next_actions": ["provide_facts"],
}
```

公共 Runtime 不导入 GIS/Economic 私有类型；组件 identity 使用稳定字符串，列表去重但保持输入的语义顺序。

## Testing strategy

- 默认只增加一个 M293 compact contract 模块，内部覆盖多组件缺失、按组件补充成功、未知字段/组件拒绝和 continuation identity mismatch。
- 相关实现完成后统一运行该模块、相邻 Planner/TaskPlan 回归、compileall、architecture strict 和 readiness；开发中只做必要的语法或单点检查。
- 真实模型、真实 GIS、Docker HTTP、浏览器和完整回归只在确实涉及的阶段收口显式执行；不重复发送昂贵 live 请求。

## Boundaries

- Always：从 catalog/RequestFacts 生成 handoff；补充后重新规划；保留脱敏 evidence；不创建未完成澄清的 run。
- Ask first：改变公共 schema 版本、持久化结构、默认 provider、CI 或引入新的外部数据源。
- Never：为某个区域/问句增加专用分支；接受 token 中未声明字段；把模型原文、prompt、密钥或私有路径写入结果。

## Success criteria

1. 多组件请求能返回按组件分组的结构化澄清，并保留原组件集合与 selection fingerprint。
2. 用户补充全部事实后生成同一组件集合的合法 TaskPlan/DAG；补充不足仍保持澄清，不创建 run。
3. HTTP、同步/异步、artifact/restart、Composite View 和 Console 对同一 continuation 的核心状态与 evidence 一致。
4. 新增一个组件 requirement 不需要修改 Runtime 主循环或前端领域分支。
5. 默认精简门禁一次覆盖该阶段独立失败模式；真实 live 只作为显式脱敏验收，不影响默认 CI。

## Open questions

- 多组件补充后是否允许用户主动删去一个已选组件：本阶段不允许，保持组件集合绑定；未来作为独立的用户确认能力规划。
