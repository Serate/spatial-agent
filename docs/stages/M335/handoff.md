# M335 阶段交接

## 状态

- 阶段：`M335` 通用多工具执行与 Provider 健康
- 状态：M335-0 阶段初始化已完成，等待实现 M335-A
- 协作：单 Agent，最大并发度 1；Docker 优先，默认测试精简

## 恢复入口

只读取 `docs/agent-work-state.md`、`tasks/current-state.md` 尾部、本文、M335 plan 当前子任务和明确列出的修改文件。不要默认读取历史阶段、全量源码、全量测试、模型原文、网页正文或敏感配置。

## 阶段输入

- M334 已建立来源 identity/quality、Bundle、Composite alignment 和网络降级，但真实跨来源请求仍会受到 Provider 时延和网络不可达影响。
- 通用 Host 已提供跨 Domain capability descriptors；验收入口必须同时理解 Host 聚合快照与 Domain 数据快照。
- RunBudget、ProgressCoordinator、ReAct、Result Registry、SSE 和前端结构化投影已经存在，应优先复用公共 seam。

## 下一步

1. 先冻结 Provider Health 安全字段与 reason code 映射。
2. 再检查通用 ReAct 的多工具连续决策和循环阻断。
3. 仅在发现真实契约缺口时修改 Runtime；每一阶段完成后更新本文和热状态并推送版本。
