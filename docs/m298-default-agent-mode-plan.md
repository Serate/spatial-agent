# M298 默认 Agent 模式与阶段可见性实施计划

## 阶段 A：默认选择边界

- 新增领域中立的产品默认配置模块。
- 读取两个受限环境变量，校验 planner/backend，提供 payload 缺省注入函数。
- CLI 默认改为真实大模型与本地后端；显式参数优先。

## 阶段 B：HTTP 产品入口

- HTTPApplication 统一为缺省请求和查询投影注入产品选择。
- FastAPI 查询参数和 stdlib 查询串不再手写 `rule + memory` 作为产品缺省。
- 保留运行时能力、发布报告等明确的本地数据诊断入口语义。

## 阶段 C：Composite 运行选择闭合

- 在 Composite Planning Application 的 canonical request 边界覆盖组件默认选择。
- 让 planner/backend 继承不改变组件身份、schema 或 execution binding 门禁。
- 增加一个两组件 contract 回归，覆盖 canonical request、binding 和执行入口。

## 阶段 D：Agent 阶段的默认可见性

- 在主结果工作区增加领域中立、紧凑的阶段条。
- 复用现有 `ConsoleResultProjection` 的阶段模型，处理初始、排队、规划、执行和终态。
- 将阶段更新接入发送、轮询、完成和错误路径；高级详情继续默认折叠。

## 阶段 E：集中验收与交付

- 只增加必要的默认配置、Composite 继承和前端阶段回归。
- 在 Docker 中集中运行 M298 与相邻契约、compileall、architecture strict 和 Node smoke。
- 使用显式配置执行一次真实模型 + 本地 GIS 验收；不把密钥、模型原文或私有数据写入仓库。
- 更新中文问题日志、milestones、任务账本和恢复快照，提交并推送阶段版本。

