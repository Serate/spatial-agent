# M322 Python 工具提案与沙箱能力图

## 目标

让默认开启的 ReAct 能够在现有工具不足时提出一个纯 Python 计算工具，并在独立、无网络、
只读、资源受限的 Docker sidecar 中完成静态校验和示例执行。验证通过只产生
`tool_proposal_receipt`，不得自动注册或在主 Runtime 中执行；M323 再接人工审批和治理状态机。

## 能力边界

| 能力 | 所属 | 输入 | 输出 | 安全边界 |
| --- | --- | --- | --- | --- |
| 提案规范化 | `agent/tooling` | 名称、说明、输入/输出 schema、源码、示例参数 | `tool-proposal.v1` | 只接受单个纯函数入口和有界 JSON schema |
| 静态检查 | `agent/tooling` | Python AST | 检查 receipt | 禁止 import、文件、网络、子进程、反射、动态执行和依赖安装 |
| 隔离执行 | Docker sidecar | 已规范化提案 | sandbox receipt | `network_mode: none`、只读根目录、tmpfs、内存/CPU/PID/超时限制 |
| ReAct `propose_tool` | `agent/react` + Runtime | 结构化提案动作 | 待审批 receipt | 不进入 ToolRegistry，不返回源码，不改变当前进程代码 |
| 后续审批 | M323 | proposal receipt + source hash | approval/registration | 本阶段不实现 |

## 数据流

```text
ReAct propose_tool
  -> decision schema
  -> Runtime policy gate
  -> proposal normalize + source hash
  -> local AST validation
  -> Unix socket sandbox sidecar
  -> repeated AST validation + isolated sample execution
  -> output JSON/schema/budget validation
  -> bounded tool_proposal_receipt
  -> react evidence / Result / artifact / recovery
  -> M323 human approval
```

## 不在 M322

- 不允许模型自动注册、修改或覆盖 ToolRegistry 工具。
- 不实现审批、拒绝、过期、撤销、版本迁移或审批 HTTP API。
- 不允许依赖安装、任意文件挂载、网络访问、shell、MCP 或主进程内动态执行。
- 不为 GIS、经济或固定专题添加专用生成模板。

## 验收面

1. 合法纯计算提案产生带 source hash 和沙箱证据的 receipt。
2. import、文件、网络、子进程、反射、动态执行和超预算代码在执行前 fail closed。
3. 参数 schema、输出 schema、JSON 预算、超时和资源异常返回稳定 reason code。
4. `propose_tool` 只进入待审批状态，不出现在 Registry，也不能被后续工具动作调用。
5. 主服务与 sidecar 使用有界 Unix socket 协议；sidecar 无网络、只读并设置资源上限。
