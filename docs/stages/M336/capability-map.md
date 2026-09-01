# M336 Capability Map：HTTP 入口收敛

| 模块 | 职责 | 依赖 |
|---|---|---|
| http-composition | 创建并关闭 Host、Service、Routing、Composite 和 HTTPApplication | Runtime、Domain Pack |
| http-semantic-dispatch | 维护 URL 到语义 action 的公共路由映射 | HTTPApplication |
| fastapi-adapter | 提供 canonical ASGI 应用和 SSE/文件响应适配 | http-composition、http-semantic-dispatch |
| stdlib-compat-adapter | 为本地旧脚本和历史测试提供轻量兼容适配 | http-composition、http-semantic-dispatch |
| entrypoint | 仅负责启动参数和部署入口，不包含业务路由 | fastapi-adapter、stdlib-compat-adapter |

构建顺序：`http-composition` → `stdlib-compat-adapter` → `entrypoint` → FastAPI 入口收敛验证。

目标不是删除标准库兼容能力，而是让根目录入口不再各自拥有一套 Composition Root、路由分派和响应契约。
