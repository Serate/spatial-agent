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

## M336-D：FastAPI 传输适配器收口

- 新增 `agent/application/fastapi_http.py`，集中 FastAPI 的依赖解析、共享路由分发、错误投影、SSE 和 artifact 响应。
- `production_api.py` 保留公开路由函数、装饰器和历史测试 seam，但仅通过适配器委托，不再自行复制 SSE/artifact 传输实现。
- 将 Domain Routing catalog/select/override/clear 统一接入共享 route metadata 与 `HTTPApplication`，防止 FastAPI 与 stdlib 语义漂移。
- 维持 FastAPI canonical、stdlib 本地兼容的部署边界；不在本阶段删除历史入口或改变 URL。
- 用 Docker 运行 HTTP、SSE、artifact、Domain Routing 和跨入口定向回归，并更新交接文档。

## 风险与回滚

- 历史测试直接导入 `AgentApiHandler`：保留同名 class 和 class attributes。
- 测试通过 patch 修改 `serve_api` globals：兼容适配器使用入口提供的动态依赖，而非导入时固定副本。
- 本阶段不删除 production endpoint，不改变 URL；若某旧测试要求静态源码，可将其迁移为行为 contract，代码保留兼容注释。
