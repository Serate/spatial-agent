# M331-B：通用任务组合矩阵

该矩阵验证公共 `general` Runtime 的能力目录、ToolRegistry、结果注册表和 Domain owner 是否能够承接不同任务形态。
它不把具体问句变成路由规则；测试只使用代表性的请求类别和已登记的能力身份。

| 请求形态 | 入口决策 | 允许的执行形态 | 必须闭合的边界 |
| --- | --- | --- | --- |
| 无外部事实的通用问题 | `request_mode=answer` | 直接回答，0 工具 | 不因无事实包误报无结果 |
| 单域事实查询 | 能力目录选择一个 owner | 一个或多个已登记工具 | schema、权限、preflight、Result owner |
| 多域查询 | 目录返回多个 component/owner | 多工具或 Composite 组合 | component identity、依赖和结果类型一致 |
| 混合问题 | 直接回答 + 受控事实 | 先执行工具，再答案生成 | 事实与答案分层，部分成功可读 |
| 能力不可用 | 目录保留 provider 降级状态 | 澄清、降级或恢复 | 不执行未就绪工具，不伪造事实 |
| 结果类型多义 | 目录无法唯一推导 | 澄清或 fail-closed | 不接受模型自造 `output_type` |

## 验收断言

- 每个公开结果类型只有一个 owner，且能在 General Result Registry 中找到对应 profile。
- 操作型工具的结果类型来自已校验 workflow/Registry；缺少操作或出现多义时不猜测。
- ToolRegistry 是唯一 dispatch 入口；模型不能通过工具名、结果标签或参数绕过 schema、权限、预算和 preflight。
- 普通问题、单域、多域和混合问题共享同一 Runtime 生命周期，不新增关键词分支。
- 部分成功、无结果、不可用和等待确认都能保留结构化状态，并交给统一答案/证据层解释。
