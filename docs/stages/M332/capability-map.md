# M332 能力地图：真实模型复杂任务有界执行与增量反馈

| 模块 id | 职责 | 依赖 |
|---|---|---|
| run-budget | 统一 Run 总预算、阶段预算、单次调用预算和安全 receipt | — |
| progress-coordinator | 在长阶段和阻塞 provider 调用期间发送有序心跳与阶段事件 | run-budget |
| provider-deadline | 将 planner、ReAct、答案 provider 调用绑定到阶段剩余预算，并报告安全尝试状态 | run-budget, progress-coordinator |
| runtime-timeout-recovery | 将预算耗尽转换为结构化失败、恢复动作和一致生命周期状态 | run-budget, progress-coordinator, provider-deadline |
| durable-timeout-fence | 处理 SQLite、reaper、重启和迟到 worker，防止终态回写污染 | runtime-timeout-recovery |
| realtime-projection | 让 SSE、轮询和前端消费同一安全进度与超时契约 | progress-coordinator, durable-timeout-fence |

构建顺序：

`run-budget → progress-coordinator → provider-deadline → runtime-timeout-recovery → durable-timeout-fence → realtime-projection`

所有模块通过公共 RunEvent、Result、Evidence 和恢复契约交互；Domain Pack、ToolRegistry、权限与数据目录不属于本阶段重构范围。
