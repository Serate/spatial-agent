# M276 Plan：Composite Coordinator 第一条执行切片

## 实施顺序

1. 新增 `agent/application/composite.py`，定义 coordinator、组件 receipt 和有界异常投影。
2. 通过 `DomainRuntimeHost.select/service` 校验并获取 Domain Service；按依赖 gate 串行调用现有 `run`。
3. 将 child payload 交给 M275 `build_composite_result_contract`，返回统一 status/result/components。
4. 编写最小 fake Host/Service 契约，覆盖正常、未知 Domain、依赖失败、独立组件失败和结果 schema。
5. Docker 运行 M276/M275 定向回归、compileall、architecture strict、quick/stage。
6. 更新恢复卡、中文问题日志、里程碑，提交推送并全局重规划下一个 transport/LLM 阶段。

## 风险

- Service 返回形状可能因同步/澄清/失败而不同：Coordinator 只读取 bounded status/domain/result/error 字段，其他字段交给 M275 projector。
- 组件请求声明的 session 可能与子 Domain 绑定冲突：为每个组件派生稳定且有界的 session id，并把冲突作为该组件失败，不污染其他组件。
- Composite 结果没有单一 Domain owner：M276 不写 artifact/SQLite，避免提前假定持久化隔离语义；后续 transport 先定义 Composite owner identity。

## Tasks

- [ ] 实现 `CompositeApplication.run()`。
- [ ] 补充 M276 coordinator contract。
- [ ] Docker 验证、文档更新、commit/push。
