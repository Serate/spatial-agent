# Plan：M332 真实模型复杂任务有界执行与增量反馈

> 顺序：全局规划 → Spec → RunBudget → 阶段心跳 → Provider/Runtime → 持久化恢复 → SSE/前端 → Docker/live 验收 → 推送/全局重规划。
> 单 Agent，最大并发度 1；默认测试精简，复杂行为集中在阶段门禁验证。

## M332-0：阶段初始化

- [x] 建立 capability map、Spec、Plan、handoff。
- [x] 切换热状态、任务账本和恢复入口到 M332。
- [x] 固定不保存模型原文、Prompt、隐藏思维链和敏感配置。

## M332-A：RunBudget

- [x] 新增统一预算模块和 `spatial-agent.run-budget.v1` receipt。
- [x] 支持总预算、规划/ReAct、执行、答案和单次 provider 调用预算。
- [x] 保持现有请求 timeout、ToolRegistry timeout 和异步 timeout 兼容。

## M332-B：阶段进度协调器

- [x] 新增可注入 event sink 的进度协调器。
- [x] 在阻塞 provider、长工具和答案等待期间发送有序 heartbeat。
- [x] 扩展安全 RunEvent 字段和重试/恢复/超时事件。

## M332-C：Provider、Planner、ReAct 与答案流

- [x] 将阶段剩余预算传入结构化调用、compact recovery、ReAct 决策和答案流。
- [x] 重试/退避不得突破阶段或总预算。
- [x] 保持结构化结果完整校验后才能展示或执行。

### M332-C 交付边界

- Provider 结构化调用与文本流支持调用级 timeout、单调 deadline 和安全进度回调；旧适配器通过参数探测保持兼容。
- Planner、ReAct、普通答案和 Composite 答案均可接收 `RunBudget`；结构化恢复使用同一阶段 deadline，答案流在增量边界检查预算。
- Provider 内部重试和退避受绝对 deadline 限制；进度回调只传递阶段、尝试、耗时、字符计数等状态，不传 Prompt、响应原文或密钥。
- 紧凑验证：M331 结构化响应 + M332 预算/进度/Provider 测试共 `17/17` 通过；未执行真实模型请求。

## M332-D：Runtime 超时与恢复

- [x] Runtime 生命周期统一开始、心跳、完成、失败和超时事件。
- [x] 为规划、执行、答案和总 Run 建立稳定错误码与恢复动作。
- [x] 保留已完成步骤、结果引用和恢复 lineage。

## M332-E：异步与持久化终态隔离

- [x] reaper 超时立即写入结构化终态和事件。
- [x] SQLite、内存和 Artifact 保护终态，阻止迟到 worker 回写。
- [x] 重启和同一 Run 恢复保持 identity 与 evidence 一致。

## M332-F：SSE/前端与阶段验收

- [x] SSE、轮询和前端识别新事件并支持断线续传。
- [x] 前端显示真实阶段、耗时、心跳、预算、重试和恢复状态。
- [x] Docker 紧凑回归、compileall、architecture strict、readiness、前端 smoke。
- [x] 完成一次真实模型 + Docker/GIS 复杂请求验收，记录脱敏证据。

## M332 阶段交付

- Runtime、异步 reaper、SQLite/Artifact 和 SSE 均使用统一的预算、阶段事件和终态 fence；迟到 worker 不得覆盖终态。
- ReAct 后续 Planner 超时不会覆盖此前成功的真实模型指标；失败与部分恢复仍通过独立 ReAct/生命周期 evidence 表达。
- Docker 定向回归 `15/15`、compileall、architecture strict、服务 smoke、readiness `200` 和规划等待/答案流/事件/结果投影 smoke 通过。
- 使用 `docker compose --env-file .env.production -f docker-compose.prod.yml ...` 挂载 `D:/dataset/agent` 后，真实模型 + 本地 GIS 复杂请求完成；异步、轮询、Artifact、SSE 断点续传和 evidence 对照通过。

## 全局重规划输入

- 产品体验：已具备真实阶段、心跳、预算、答案增量和可恢复证据；下一步关注复杂请求的答案质量与用户可理解性，而非增加技术状态数量。
- Runtime：预算、生命周期和持久化终态边界已闭合；后续只在跨入口差异或真实失败证据出现时继续抽象。
- Planner：开放 ReAct 已可组合已登记能力；下一步验证多领域开放请求的选择稳定性、有限恢复和工具调用效率。
- Domain/数据：GIS 本地数据链路已完成真实验收；继续扩展能力目录和数据发现证据，不把单个区域写成 Runtime 分支。
- 部署/测试：Docker 生产演示需固定 `--env-file` 与卷检查；默认保持离线紧凑测试，live 仅作为显式验收。

## 交付规则

- 每个子任务开始、完成或暂停时先更新 `tasks/current-state.md`，再追加 `tasks/task-progress.md` 和 `docs/agent-work-state.md`。
- 阶段完成时更新 handoff、索引、开发问题日志，提交并推送版本。
- 阶段结束后从产品、Runtime、Planner、Domain、数据、模型、部署、体验和测试全局重规划。
