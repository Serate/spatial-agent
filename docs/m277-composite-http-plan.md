# M277 Plan：Composite HTTP 统一入口

## 实施顺序

1. 在 HTTPApplication 增加 `composite_run` 语义命令，并注入 M276 Coordinator。
2. 在 FastAPI 与 stdlib 入口增加 `/composite-runs` 路由；保持错误投影和 URL 胶水本地化。
3. 补充 Application contract 与 Docker 生产启动检查。
4. 用 Docker 运行精简 CI/stage，并提交一条真实 Docker HTTP GIS + Economic 组合验收。
5. 更新中文恢复卡、问题日志、里程碑，提交推送并规划 async/artifact/restart 阶段。

## 风险与缓解

- Composition Root 变量命名不一致会导致生产入口 import 失败：每次 HTTP 入口改动都必须重建镜像并请求 `/health/ready`。
- 两个 transport 可能只在其中一个加入路由：静态检查和两入口共享 Application contract 同时验证。
- Composite 结果被压缩或重新包装：HTTP contract 只允许透传 Coordinator response，不重新解释 nested Result。

## Tasks

- [ ] 完成 `composite_run` Application dispatch。
- [ ] 完成两个 HTTP 入口路由。
- [ ] Docker HTTP/CI/stage 验收与文档提交。
