# M262 架构收敛实施 Plan

本阶段遵循：全局约束确认 → spec → 实现 → Docker 验证 → 文档/提交 → 全局重规划。

状态：已完成

## A. 生命周期阶段化（最高优先级）

1. 为生命周期建立内部上下文对象，集中保存 resolved request、RequestFacts、context packet、Result、candidate plan、repair lineage、执行结果和 deadline。
2. 将 `run()` 拆成显式 `resolve`、`clarify`、`plan`、`validate_repair`、`execute`、`answer`、`evidence/finalize` 阶段。
3. 保持 decision resume、direct answer、confirmation、cancel/timeout、有限 repair/replan 和所有失败状态的既有行为。
4. 增加少量阶段契约测试，避免复制旧测试矩阵。

## B. HTTP 传输胶水收敛

1. 识别 `serve_api.py` 与 `production_api.py` 的纯传输重复。
2. 新增共享 transport 辅助模块，收敛请求读取、JSON 编解码、错误映射和 artifact JSON 投影。
3. 逐步替换 stdlib handler 与 FastAPI wrappers，保持 URL、状态码和响应 envelope 不变。
4. 用现有 HTTP contract 和一条 artifact manifest/evidence 回归验证对等性。

## C. 架构守卫清单纠正

1. 把 `COMPAT_MODULES` 改为语义明确的 shim/facade 清单。
2. 将真实公共模块移出豁免名单。
3. 为清单增加静态契约，防止真实模块再次混入。
4. 保持当前顶层导入守卫范围，并把递归 lazy import 检查列为后续阶段，不在本阶段引入无关行为变化。

## 阶段验收

- Docker `compileall`。
- Docker `architecture strict`。
- M262 定向测试。
- Docker `quick` 与 `stage`。
- 记录未能启动的环境依赖，不用本机 Python 结果替代 Docker 结论。

本阶段结果：Docker 全量 `compileall agent scripts tests`、architecture strict、quick、stage 通过；M262、Decision、HTTP、profile contract 共 40 项定向回归通过。

## 暂不做

- 不删除旧兼容入口。
- 不重写全部 FastAPI 路由。
- 不修改 GIS 工具算法、真实数据和前端展示。
- 不把真实模型接入默认测试。
