# M323 人工审批、持久化和 Registry 治理能力图

## 目标

把 M322 产生的已验证 Python 工具提案纳入显式人工决策生命周期。批准之前只能查看 receipt，
批准之后才允许生成版本化 Registry 工具；拒绝、过期、撤销和重启恢复都必须可审计。

## 能力边界

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| approval-record | 规范化审批请求、状态转换和决策 receipt | M322 proposal receipt |
| approval-store | SQLite 持久化、幂等写入和重启恢复 | approval-record |
| registry-release | 将批准的提案转为版本化受控工具定义 | approval-record、ToolRegistry |
| approval-application | CLI/HTTP 的查询、批准、拒绝、撤销语义 | approval-store、registry-release |
| runtime-gate | 执行前检查批准状态、版本和权限快照 | approval-store、ToolRegistry |
| projection | 向 Result/Evidence/前端投影脱敏状态 | approval-record、runtime-gate |

## 依赖方向

```text
M322 receipt → approval-record → approval-store
                         ↓
                  registry-release → runtime-gate → Result/Evidence/View
                         ↑
                approval-application
```

## 不在本阶段

- 不自动批准模型提案。
- 不在主进程执行未批准源码。
- 不改变已有静态工具权限，不引入任意代码加载、包安装或网络访问。
- 不把审批实现成绕过 ToolRegistry 的旁路。
