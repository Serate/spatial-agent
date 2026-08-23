# Agent 当前恢复卡

本文件是新对话或上下文压缩后的唯一默认状态源。默认不要打开其他上下文文档、归档、完整测试、模型响应或数据文件。

## 目标

建设可测试、可观测、可替换、可恢复的通用 Agent Runtime，GIS 只是业务载体。

## 当前阶段

M221-B1 已完成：同步结果、异步轮询和前端异步摘要共享公共 `project_model_evidence` Module；前端 view 动态渲染保持通过。

## 已验证

- Docker 精简回归 37/37；M194/M195/M220 组合回归 33/33；`compileall` 返回 0。
- production acceptance：`ready`；真实数据、同步/异步、artifact、预览指纹和失败契约通过。
- 明确“建设适宜性”请求走专用能力；泛化“适合建设”请求保持通用地形/土地利用能力。
- M221 前端静态契约 13/13；健康 view、空间总览、Leaflet/SVG 地图 smoke 通过。
- 真实模型 + 本地 GIS Docker live case 1/1（6585 tokens），live baseline replay 4/4；M148 Docker recorded replay 的 text/GIS 两类 case 均完成，重启后模型调用为 0。
- M135/M136/M137/M146/M148 model/context/evidence 回归 20/20；实际异步 smoke 返回版本化模型证据、上下文指纹和 artifact 引用；Docker `compileall` 返回 0。

## 下一阶段

按全局能力矩阵继续实现：验证 live 请求在 HTTP/异步/artifact/前端入口的同一结果投影；随后删除剩余旧前端 renderer，并补齐重启接管的 live evidence 验收。

## 不变量

- Runtime 保持领域中立；新增能力扩展 facts、catalog、schema、workflow、result/view，不写区域或固定问句分支。
- 默认测试离线且精简；真实模型、GIS、Docker、HTTP 和浏览器只走显式验收。
- 不提交 API key、`.env.production`、原始模型响应、真实数据或私有路径。

## 读取预算

- 默认只读本卡；源码最多按需 2 个文件，测试最多先读 1 个文件。
- 需要历史时只用恢复脚本的 `-Topic` 有界检索，不全文读取历史文件。
- 本卡超过 2KB 就压缩，只保留目标、阶段、阻塞、下一步、最近证据和约束。
