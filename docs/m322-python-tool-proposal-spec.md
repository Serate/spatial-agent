# Spec：M322 Python 工具提案与 Docker 沙箱

## Objective

为受控 ReAct 增加 Python 工具提案验证能力。模型只能提交一个符合公共契约的纯计算函数；
Runtime 必须先完成结构化校验和 AST 检查，再交给无网络 Docker sidecar 执行一组示例参数。
验证通过的提案仍处于待审批状态，不得注册或执行为正式工具。

## Public contracts

### Tool proposal

版本：`spatial-agent.tool-proposal.v1`。

必需字段：

- `name`：小写工具标识符，最长 96 字符，不能与 Registry 现有工具重名。
- `description`：面向审批者的短说明，最长 400 字符。
- `input_schema`、`output_schema`：对象类型 JSON schema。
- `source`：最多 48 KiB，只允许定义 `def run(arguments): ...`。
- `example_arguments`：符合 input schema 的对象，用于一次隔离验收。

### Sandbox receipt

版本：`spatial-agent.tool-proposal-receipt.v1`。

只保留：proposal ID、名称、状态、source hash、schema hash、检查状态、耗时、输出字节数、
reason code 和沙箱 profile。不得包含源码、示例参数、原始输出、Prompt、模型原文、环境变量或路径。

状态：`validated|rejected|unavailable`。`validated` 只表示可以进入 M323 人工审批，不表示已批准。

## Source policy

- 顶层只允许一个名为 `run` 的同步函数和常量赋值；禁止 import、class、decorator、async、yield、
  global/nonlocal、try/raise、with、lambda 和名称以 `__` 开头的访问。
- 调用只允许固定纯函数 builtins；禁止属性调用、`open`、`eval`、`exec`、`compile`、反射、
  环境变量、网络、子进程和包安装。
- 限制源码长度、AST 节点数、嵌套深度、循环、输出字节数和执行时间。
- sidecar 必须重复静态检查，不能信任主 Runtime 的预检 receipt。

## Sandbox transport

- 主服务通过 Unix domain socket 发送单个有界 JSON envelope；不挂载 Docker socket。
- sidecar 使用同一应用镜像，`network_mode: none`、只读根文件系统、独立 tmpfs、非 root 用户、
  内存/CPU/PID 上限和健康检查。
- worker 为每次执行创建独立临时目录和受限子进程，stdin/stdout 使用有界 JSON；超时后终止子进程。
- socket 不可用时返回 `sandbox_unavailable`，不得回退到主进程执行。

## Runtime integration

- ReActLoop 增加可选 `validate_proposal` seam；没有 validator 时保持结构化 unavailable。
- Runtime 在 accepted 前校验提案开关、名称冲突和 schema；验证 receipt 进入安全 ReAct evidence。
- 本阶段终态为 `react_tool_proposal_awaiting_approval`，运行不得自动继续调用该工具。
- CLI、HTTP、异步、artifact 和 SQLite 继续消费同一 `react_evidence`；M323 再增加审批应用接口。

## Testing

- 默认离线：proposal normalize、AST policy、协议上限、receipt 脱敏、ReAct/Runtime 待审批状态。
- Docker sidecar：合法纯计算、输入错误、输出 schema 错误、超时、网络/import/文件/子进程拒绝。
- 相邻回归：M322、M321、M320、compileall、architecture strict、service readiness。
- 不调用真实模型；真实模型 + 提案 + 审批 + 注册留到 M325。

## Acceptance criteria

1. 合法提案在 sidecar 中完成示例执行并返回 `validated` receipt。
2. 危险或超预算源码不进入执行阶段，稳定返回 `rejected`。
3. sidecar 不可用时安全失败，主服务不执行生成代码。
4. receipt 可持久化和恢复且不含源码、参数、输出或敏感配置。
5. Registry 在 M322 前后工具集合不因提案自动变化。
