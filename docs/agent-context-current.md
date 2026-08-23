# Agent 当前恢复卡

本文件是新对话或上下文压缩后的唯一默认状态源。默认不要打开历史文档、完整测试、模型响应或数据文件。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前阶段

M221-B2 已完成：新增 opt-in 的 live HTTP/异步/artifact 验收；同步、异步轮询、artifact、manifest/evidence 共享稳定结果投影，并修复模型证据重复投影时 `available` 状态漂移。

## 已验证

- Docker rule+memory HTTP 验收通过：sync、async、artifact、evidence、幂等和 view/workspace 六组比较均为 `ok`。
- 真实 DeepSeek 中转 + Docker 验收通过：sync/async 均完成，异步证据记录 5228 tokens；未保存或输出原始模型响应。
- M135/M146 受影响回归 12/12，Docker `compileall` 通过；既有 compact、生产、GIS、浏览器和 replay 基线保持有效。

## 下一阶段

从全局恢复能力继续：补齐进程重启接管后的 live evidence 同一性；随后删除剩余旧前端 renderer，并对 CLI/HTTP/前端/Artifact 的最终结构化边界做一次收敛审计。

## 不变量

- Runtime 领域中立；新增能力扩展 facts、catalog、schema、workflow、result/view，不写区域或固定问句分支。
- 默认测试离线且精简；真实模型、GIS、Docker、HTTP 和浏览器只走显式验收。
- 不提交 API key、`.env.production`、原始模型响应、真实数据或私有路径。

## 读取预算

- 默认只读本卡；源码最多按需 2 个文件，测试先读 1 个文件。
- 历史只用 `scripts/resume_context.ps1 -Topic` 有界检索；本卡超过 2KB 时先压缩。
