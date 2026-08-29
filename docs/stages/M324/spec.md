# Spec：M324 受控工具治理可见化与重启再绑定

## Objective

让 M323 的人工审批不只停留在数据库和后端接口中：服务重启后，仍处于 approved 且版本/指纹
有效的工具能够通过受控 handler 重新绑定到 ToolRegistry；控制台能够查看 pending、approved、
rejected、expired、revoked 和 invalid 状态，并在需要时提交批准、拒绝或撤销动作。

用户可见信息必须是有界投影，不展示源码、示例参数、Prompt、模型原文、密钥或完整内部轨迹。
审批动作仍必须经过 `HTTPApplication`，FastAPI 和 stdlib 只负责传输适配。

## Assumptions

1. M323 的 `tool-approval.v1`、SQLite schema 和 HTTP 语义保持兼容，不新增审批角色系统。
2. sandbox handler 只引用 proposal identity 和 source hash；服务不会从 approval record 读取或执行源码。
3. 控制台继续使用 `web/src` → `web/dist` 构建链，不迁移 React，也不改 Runtime/Planner 契约。
4. `approved` 记录在 handler 不可用时只能形成明确 degraded 状态，不能绕过 Registry 或直接执行。

## Public contract

- 复用 `spatial-agent.tool-approval.v1` 和现有 `tool_approvals`、`tool_approval`、
  `tool_approval_resolve` application action。
- 新增的恢复投影（如需要）必须有独立版本号，字段仅包含 approval id、工具名、状态、版本、
  指纹摘要、允许动作、恢复状态和安全原因码。
- Registry binding 必须记录 `approval_id`、`approval_version`、`approval_fingerprint`；
  dispatch 前继续由 Runtime approval gate 二次读取持久化状态。

## Project structure

- `agent/application/service_state.py` / `agent/service.py`：Runtime 创建和 approved binding 恢复 seam。
- `agent/tooling/approval.py` / `agent/tools.py`：审批记录与 Registry gate。
- `agent/application/http.py`：共享审批读取与决策语义。
- `web/src/console_app.js` 和新增 `web/src/console_tool_approvals.js`：用户投影和动作交互。
- `tests/test_m324_tool_governance.py`：紧凑后端/跨入口契约；必要的 Node smoke 只覆盖 DOM 投影。
- `docs/stages/M324/`：本阶段能力图、Spec、Plan 和交接。

## Commands

- Build: `docker compose -f docker-compose.prod.yml build spatial-agent tool-proposal-sandbox`
- Restart: `docker compose -f docker-compose.prod.yml up -d --force-recreate spatial-agent tool-proposal-sandbox`
- Compact test: `docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m324_tool_governance -v`
- Regression: `docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m323_tool_approval tests.test_m322_tool_proposal`
- Frontend build: `docker exec ai-agent-spatial-agent-1 python scripts/build_console.py`
- Gates: `python -m compileall -q agent domains scripts`、`scripts/architecture_check.py --strict`、
  `scripts/validate_code_index.ps1`、`scripts/validate_document_index.ps1`、`GET /health/ready`

## Code style

恢复器接受依赖并返回有界结果，不在调用方拼接审批策略：

```python
def rehydrate_approved_tools(runtime, records, handler_factory):
    """Publish only approved, version-matched records through ToolRegistry."""
    return [
        registry.register_approved_tool(record, handler)
        for record, handler, registry in _valid_bindings(runtime, records, handler_factory)
    ]
```

实现必须保持单一 Registry seam；兼容 facade 只能转发，不复制恢复逻辑。

## Testing strategy

- 后端紧凑契约：服务重启后的 approved rehydration、handler 不可用降级、revoked/version drift
  fail closed、重复恢复幂等。
- 跨入口契约：HTTPApplication、FastAPI 和 stdlib 对列表/详情/决策返回同一核心投影；不重复
  现有 M323 全量测试，只增加本阶段独立失败模式。
- 前端：Node DOM projection smoke 验证状态层级、动作按钮和敏感字段不出现；样式微调不重复
  运行业务测试。
- 阶段收口：Docker 紧凑契约、M322/M323 回归、compileall、architecture strict、索引校验、
  readiness；不调用真实模型。

## Boundaries

- Always：所有恢复工具经过 ToolRegistry；版本/指纹、权限、schema 和 approval gate 继续校验；
  用户界面只显示安全投影。
- Ask first：改变 approval schema、审批角色、沙箱网络策略、默认自动批准行为或引入前端框架。
- Never：自动批准；执行未批准源码；从数据库/HTTP payload 读取源码执行；暴露 Prompt、密钥或
  模型原文；复制 FastAPI/stdlib 业务语义。

## Success criteria

1. 服务首次创建 Runtime 时，approved 且有效的工具可从 SQLite record 重新绑定到 Registry；
   pending/rejected/expired/revoked/invalid 不会绑定。
2. handler 或 sidecar 不可用时，恢复结果明确为 degraded/unavailable，dispatch 仍安全失败。
3. 同一 approval 重启恢复幂等；撤销或版本/指纹漂移后，旧 binding 无法执行。
4. 控制台能读取有界审批状态并提供符合状态的人工动作，动作结果清晰反馈。
5. HTTPApplication、FastAPI、stdlib、SQLite/restart 和 Console 使用一致的 approval identity。
6. Docker 精简验证通过，默认不调用真实模型，不保存敏感数据。

## Open questions

- 是否在后续阶段为审批变更增加独立 RunEvent：本阶段不新增，先复用 approval HTTP 投影和现有
  runtime evidence，避免把管理动作伪装成分析 Run。
