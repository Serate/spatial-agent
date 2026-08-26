# M307 Agent Runtime 边界收敛能力图

## 目标

从项目整体目标出发，补齐 Runtime 仍然存在的结构性边界问题：让生命周期编排按阶段可读、可测试、可恢复；让 FastAPI 与 stdlib 入口共享传输语义；让架构守卫准确区分兼容 shim 与公共实现。GIS、Economic 和开放式组合能力继续作为 Domain Pack，不在本阶段增加专题分支。

## 能力模块

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| runtime-phase-pipeline | 将单体运行循环收敛为 resolve → clarify → plan → validate/repair → execute → answer → evidence 的显式内部阶段，保持统一生命周期与结果契约 | — |
| transport-boundary | 抽取 HTTP 方法、路径、查询、JSON 和状态码的共享边界，使 FastAPI 与 stdlib 入口只保留部署适配 | runtime-phase-pipeline |
| compatibility-governance | 校准 `COMPAT_MODULES`、shim 和公共实现分类，收紧架构守卫，保证迁移和导入兼容性可观测 | runtime-phase-pipeline |
| acceptance-and-release | 使用 Docker 验证阶段行为、跨入口和架构边界，更新中文记忆、任务账本并推送版本 | runtime-phase-pipeline, transport-boundary, compatibility-governance |

## 构建顺序

`runtime-phase-pipeline → transport-boundary → compatibility-governance → acceptance-and-release`

## 不在本阶段

- 不增加 GIS、Economic 或其它专题工具。
- 不重写 TaskPlan、ToolRegistry、Result、Artifact、Evidence 的公共 schema。
- 不把 provider、模型原文或内部思维过程暴露给前端。
- 不把默认 CI 扩大为全量测试；Docker 阶段收口只保留独立失败模式门禁。
