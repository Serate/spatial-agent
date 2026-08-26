# M307 Agent Runtime 生命周期与传输边界实施计划

## A：基线与阶段契约

- 以 M306 的 Composite Result、Evidence、TaskPlan 和 binding 验收结果为基线。
- 记录 `run_lifecycle.py` 当前阶段、状态、receipt 和异常出口，冻结不变量与兼容矩阵。
- 输出最小阶段契约测试，先证明现状和目标边界。

状态：待开始。

## B：显式生命周期阶段流水线

- 将 resolve、clarify、plan、validate/repair、execute、answer、evidence 拆为私有阶段函数或小型阶段对象。
- 每个阶段只接收上阶段结构化结果，保留一次 repair、TaskPlan/DAG、ToolRegistry 和 execution binding 门禁。
- 保持现有状态、artifact、异步、SQLite/restart 和答案/evidence 投影。

状态：待开始。

## C：共享传输边界

- 盘点 `production_api.py`、`serve_api.py` 和 `application/http.py` 的 URL/query/JSON/status 语义。
- 抽取共享 request decoding、route resolution、response encoding 和错误状态映射；FastAPI 与 stdlib 入口只做适配。
- 用代表性同步、异步、artifact 和错误请求验证两入口结果一致。

状态：待开始。

## D：兼容治理与守卫收口

- 根据实际 imports 将 shim、facade 和真实公共模块分别登记。
- 移出真实公共引擎模块的 compat 豁免，更新 `architecture_check.py` 的严格检查和最小兼容测试。
- 仅在确认没有依赖后处理可删除 shim；若保留则明确迁移说明和淘汰条件。

状态：待开始。

## E：Docker 集成验收

- 重建并强制重启 Docker。
- 集中运行本阶段契约、相邻 Runtime/Composite 回归、compileall、architecture strict、Node projection、Service smoke、readiness、HTTP/artifact/restart acceptance。
- 只有离线门禁发现 provider-facing 行为确有变化时，才进行一次显式真实模型验收；不重复无必要 live 请求。

状态：待开始。

## F：文档、版本和全局重规划

- 更新中文问题日志、milestones、历史恢复卡、任务账本、快照和 README 引用。
- 提交并推送一个阶段版本。
- 从产品、架构、数据、模型、部署、体验、测试七个维度重规划下一阶段，不陷入单一数据集或单个入口。

状态：待开始。

## 交付顺序

`A → B → C → D → E → F`

开发阶段只做必要的静态/契约检查；B～D 合并后集中执行 E 的精简门禁，避免测试次数随拆分任务线性增长。
