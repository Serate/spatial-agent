# M336 阶段交接

## 状态

- 阶段：`M336` HTTP 入口收敛
- 状态：M336-A～C 已实现并完成 Docker 定向验收，待提交推送
- 协作：单 Agent，Docker 优先，最小充分验证

## 恢复入口

只读取本文、`docs/agent-work-state.md`、`tasks/current-state.md`、M336 plan 当前子任务和明确列出的源码/测试文件。不要默认读取完整历史或全部 HTTP 文件。

## 当前任务

1. 提交本阶段代码与文档变更，并推送阶段版本。
2. 后续全局重规划时评估 FastAPI 路由胶水、兼容 facade 和历史测试债务。

## 禁止事项

- 不提交密钥、模型原文、Prompt 或运行产物。
- 不用修改测试断言掩盖生产路由漂移。
- 不在 `HTTPApplication` 之外复制语义 action。

## 本阶段已完成

- `agent/application/http_composition.py` 成为 Host、Service、DomainRouting、Composite 和 `HTTPApplication` 的共享装配根。
- `agent/application/stdlib_http.py` 集中标准库入口的 URL/query/JSON、错误投影、artifact、SSE 和静态资源适配。
- `production_api.py` 与 `serve_api.py` 均使用共享装配；`serve_api.py` 仅保留启动入口、兼容导出和动态 patch seam。
- 保留 `AgentApiHandler`、运行时能力快照和 release evidence 等历史调用面；显式测试 artifact root、`max_files` 边界及每请求重绑定 Service。
- 过期静态测试已迁移为“serve 入口委托 stdlib adapter”的结构契约；省略 planner/backend 的历史 HTTP 测试改为显式离线选择，避免误触发真实模型网络。

## 验证结果

- Docker 定向回归：`tests.test_m78_http_contract tests.test_http_contract tests.test_m10_api_service tests.test_m60_runtime_capabilities_contract tests.test_m165_cross_entry_contract`，**30/30 通过**。
- Docker：`python -m compileall -q agent production_api.py serve_api.py` 通过。
- 服务：`http://127.0.0.1:8088/health/ready` 返回 HTTP 200。
- `git diff --check` 无空白错误；仅有 Git 的工作区换行提示。
- 测试期间出现的既有 `ResourceWarning`（观测日志句柄）未改变测试结果，留作后续独立资源治理项。

## 当前未提交变更

- 入口收敛：`production_api.py`、`serve_api.py`、`agent/application/http_composition.py`、`agent/application/stdlib_http.py`。
- M163/M66 历史回归修复及对应文档/测试变更仍与本阶段同处工作区，提交前需用 `git diff --stat` 核对，不要覆盖用户已有修改。
- 未跟踪 `.claude/` 不属于本阶段，暂不处理。
