# M324 阶段交接

## 当前状态

- 阶段：M324 受控工具治理可见化与重启再绑定
- 当前任务：阶段已收口，进入 M325
- 状态：已完成
- 恢复入口：`docs/agent-work-state.md`、`tasks/current-state.md`、本文件

## 已完成

- M324-A：新增 `agent/tooling/rehydration.py`，Runtime 构造时从 approval store 读取 approved
  记录；仅调用 validator 的 `handler_for` 和 Registry 的 `register_approved_tool`。非 approved、
  领域不匹配、handler 不可用、重复绑定或版本/指纹漂移均不进入 Registry，并返回有界恢复证据。
- M324-A：执行策略在恢复后再建立，恢复的工具会进入 Runtime 的已知工具集合；Registry 对相同
  approval_id 的旧版本绑定增加 stale 检查。
- M324-B：新增 `spatial-agent.tool-approval-visibility.v1`，HTTP 列表、详情和动作响应提供
  `visibility`；保留旧 `approval` 兼容字段，但 Console 不消费定义字段。
- M324-C：新增 `web/src/console_tool_approvals.js`，工具治理默认折叠，显示状态、恢复状态、
  版本和允许动作；动作完成后刷新，失败保留分析结果并显示安全错误。

## 必要文件

- `docs/stages/M324/capability-map.md`
- `docs/stages/M324/spec.md`
- `docs/stages/M324/plan.md`
- `agent/tooling/rehydration.py`
- `agent/tooling/approval.py`
- `agent/tools.py`
- `agent/runtime.py`
- `agent/service.py`
- `agent/application/http.py`
- `web/src/console_tool_approvals.js`
- `web/src/console_app.js`
- `web/src/index.html`
- `web/src/styles.css`
- `tests/test_m324_tool_governance.py`
- `scripts/console_tool_approvals_smoke.js`

## 验证与阻塞

- Docker M324 契约 6/6、M323/M322 回归 18/18、Node projection smoke、compileall、
  `architecture_check.py --strict`、代码/文档索引校验和 `/health/ready` HTTP 200 均通过。
- 本阶段未调用真实模型；真实模型、真实 GIS 和白名单网络验收移交 M325。

## 下一步

1. 读取 `docs/stages/M325/handoff.md`、`spec.md` 和 `plan.md` 恢复后续工作。
2. 使用 M325 的显式脚本完成真实模型、Docker/GIS 和白名单搜索验收。
