# M324 能力图：受控工具治理可见化与重启再绑定

## 范围

M323 已完成审批状态机、SQLite 持久化、Registry gate 和 HTTP 语义。本阶段把这些后端能力
接入服务恢复与控制台，让用户能看到治理状态，并确保服务重启后 approved 工具仍通过受控
Registry seam 恢复；不扩展审批角色模型，不改变 Python 沙箱安全边界。

| 模块 id | 职责 | 依赖 |
|---|---|---|
| approval-rehydration | 从持久 approval record 恢复 approved 工具的 Registry binding | M323 approval store、ToolRegistry、sandbox handler |
| approval-visibility | 为控制台提供有界审批状态、动作和错误投影 | M323 HTTPApplication |
| approval-console | 在现有结果工作区显示审批状态和人工动作 | approval-visibility、现有 Console 资源 seam |
| governance-acceptance | 验证重启、双 HTTP 入口、前端投影和安全 fail-closed | 前三个模块 |

## 构建顺序

`approval-rehydration` → `approval-visibility` → `approval-console` → `governance-acceptance`

单 Agent 顺序实施，模块之间不并行修改同一工作树。
