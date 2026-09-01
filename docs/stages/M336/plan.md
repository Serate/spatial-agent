# M336 Plan：HTTP 入口收敛

## M336-A：共享 Composition Root

- 新增 `HTTPComposition`，集中创建/关闭 Host、Service、DomainRouting、Composite 和 `HTTPApplication`。
- 两个入口改为使用同一装配工厂，保留可替换的模块级兼容名称。
- 验证导入、readiness 和资源关闭。

## M336-B：标准库兼容适配器

- 将 stdlib Handler 的路径、query、JSON、错误、artifact 和 SSE 适配集中到 `agent/application/stdlib_http.py`。
- `serve_api.py` 只保留兼容导出、公共配置别名和启动参数。
- 所有业务 action 经 `resolve_route` 与 `HTTPApplication` 执行。

## M336-C：入口契约收口

- 增加/调整 HTTP contract，验证 FastAPI 与 stdlib 的路由 action 和错误投影一致。
- 更新 API 文档与兼容矩阵，说明 canonical 入口与兼容入口。
- Docker 编译、定向测试、readiness 和最小 HTTP acceptance。

## 风险与回滚

- 历史测试直接导入 `AgentApiHandler`：保留同名 class 和 class attributes。
- 测试通过 patch 修改 `serve_api` globals：兼容适配器使用入口提供的动态依赖，而非导入时固定副本。
- 本阶段不删除 production endpoint，不改变 URL；若某旧测试要求静态源码，可将其迁移为行为 contract，代码保留兼容注释。
