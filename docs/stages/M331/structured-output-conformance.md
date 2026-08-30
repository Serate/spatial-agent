# M331-A：结构化模型输出一致性矩阵

本矩阵只记录脱敏的输出类别、处理决策和可观测结果，不保存模型原文、Prompt、密钥或网页正文。所有场景都必须经过
调用方的 TaskPlan、ReAct、Composite 或 Answer schema 校验；“可修复”不等于可以绕过权限、工具注册或结果契约。

| 场景 | 典型表现 | 公共边界处理 | 终态/证据 |
| --- | --- | --- | --- |
| 合法对象 | 返回目标 schema 的 JSON 对象 | 直接交给调用方严格校验 | accepted，0 次恢复 |
| 有界包装 | JSON fence 或完整的 `<think>…</think>` 后跟 JSON | 仅去除完整、明确的包装；不接受前后夹杂自然语言 | accepted，记录正常调用 |
| 字段别名 | `content`/`text`/`response` 代替 Answer 的 `answer`，或 ReAct 工具别名 | 仅在唯一别名、无冲突时本地修复；随后重新严格校验 | repaired 或 invalid |
| 额外字段 | 合同未声明的顶层字段 | 公共层不盲目删除；调用方的白名单决定是否拒绝，已知 ReAct 动作可使用动作级白名单 | invalid 或 bounded repair |
| 漏字段 | 缺少 `goal`、动作必需字段或 Answer 内容 | 不猜测事实、工具、结果类型；可用一次紧凑校正请求补齐 | repaired 或 invalid_model_response |
| 截断 JSON | finish reason 为 length、空内容或 JSON 不完整 | 最多一次 compact recovery；第二次仍无效则安全终止 | invalid_model_response，最多 1 次恢复 |
| 错误结果类型 | 模型给出未登记或与可信 workflow 冲突的 `output_type` | 以 Registry/workflow 推导为准；无法唯一推导则澄清或拒绝 | blocked/clarification，不执行 |
| Provider 超时 | 网络超时、连接失败或超时预算耗尽 | 按 Provider deadline 分类；只在传输策略允许时重试，不当作模型格式错误 | provider_timeout/provider_network |
| 非对象响应 | 数组、纯文本或无法提取结构化内容 | 转为稳定的 `invalid_model_response`，不进入前端计划或执行 | planning/answer failure |

## 有界规则

- 每个结构化请求最多一次 compact recovery；恢复响应不再由公共层递归重试。
- 本地字段修复只处理显式登记且无冲突的别名，不改变值的类型，不生成缺失值。
- Plan 和 ReAct 的完整 schema、工具 allowlist、参数、依赖、结果类型和权限仍由原有边界复核。
- Answer 的修复只改变用户答案字段形状；事实仍来自 Runtime 结果包，内部引用和敏感内容继续拒绝。
- 所有错误证据只保留阶段、类别、reason code、是否可重试和恢复次数。

## 验收场景

M331-A 的紧凑测试覆盖：Planner 截断后一次恢复、ReAct 非对象/字段别名、Answer 字段别名和额外字段拒绝、第二次恢复
仍无效时终止、错误结果类型不执行，以及 Provider timeout 保持 Provider 分类。真实模型验收只保存上述状态和计数。
