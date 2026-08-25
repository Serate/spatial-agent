# M293 多组件事实协调与可恢复 Composite 续跑能力图

## 全局缺口

M292 已能让单个 Planner 组件声明缺失事实、生成 continuation，并在补充后重新走 context、Planner 和 TaskPlan 门禁。当前系统仍缺少多组件统一澄清：一个开放式请求同时选择 GIS 与 Economic 能力时，不能只为第一个组件发 token，也不能让补充一个组件后丢失另一个组件的选择、事实和证据。

本阶段服务于通用 Agent Runtime 的开放式、多领域闭环，不新增 GIS/Economic 专题流程，不改变 Runtime、ToolRegistry 或 Result 主契约。

## 能力模块与依赖

| 模块 ID | 职责 | 依赖 |
|---|---|---|
| aggregate-handoff | 将多个已选组件的公共 requirements、已知事实、缺失字段和 workflow 约束汇总为一个有界 handoff | M292 component-fact-handoff |
| composite-continuation | 签发并校验绑定组件集合的 continuation，合并分组件补充事实并重新规划 | aggregate-handoff、现有 Planner/TaskPlan gate |
| cross-entry-projection | 让 HTTP、同步/异步提交、artifact、restart、Composite View 和 Console 使用同一多组件状态 | composite-continuation、现有生命周期 |
| acceptance-harness | 用少量 replay fixture 验证成功、部分缺失、补充后成功和身份篡改；保留一次显式 live 入口 | 前三个模块 |

## 构建顺序

`aggregate-handoff → composite-continuation → cross-entry-projection → acceptance-harness → 全局重规划`

所有模块顺序实施，最大并发度为 1。一个阶段任务包应覆盖契约、实现、集成、文档和交付准备；测试按独立失败模式集中运行，不按任务数增加测试轮次。
