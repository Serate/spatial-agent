# M307 Agent Runtime 边界收敛能力图

## 目标

从项目整体目标出发，补齐 Runtime 仍然存在的结构性边界问题：让生命周期编排按阶段可读、可测试、可恢复；让 FastAPI 与 stdlib 入口共享传输语义；让架构守卫准确区分兼容 shim 与公共实现。GIS、Economic 和开放式组合能力继续作为 Domain Pack，不在本阶段增加专题分支。

## 能力模块

| 模块 ID | 责任 | 依赖 |
|---|---|---|
| runtime-phase-pipeline | 审计并保持 resolve → clarify → plan → validate/repair → execute → answer → evidence 的显式内部阶段，保持统一生命周期与结果契约 | — |
| transport-boundary | 验证 HTTPApplication/http_transport 已集中语义、查询、JSON、错误和 artifact 边界；FastAPI 与 stdlib 仅保留框架适配 | runtime-phase-pipeline |
| compatibility-governance | 验证 `COMPAT_MODULES`、shim 和真实公共模块分类，保证架构守卫覆盖真实引擎 | runtime-phase-pipeline |
| acceptance-and-release | 使用 Docker 验证阶段行为、跨入口和架构边界，更新中文记忆、任务账本并推送版本 | runtime-phase-pipeline, transport-boundary, compatibility-governance |

## 构建顺序

`runtime-phase-pipeline → transport-boundary → compatibility-governance → acceptance-and-release`

## 不在本阶段

- 不增加 GIS、Economic 或其它专题工具。
- 不重写 TaskPlan、ToolRegistry、Result、Artifact、Evidence 的公共 schema。
- 不把 provider、模型原文或内部思维过程暴露给前端。
- 不把默认 CI 扩大为全量测试；Docker 阶段收口只保留独立失败模式门禁。

## 基线结论

本阶段审计确认以上三个能力在既有 M262 结构中已经成立：`run_lifecycle.py` 已有显式阶段，两个 HTTP 入口共同使用 `HTTPApplication` 与 `http_transport`，真实公共模块不在 compat 豁免中。剩余的 FastAPI 装饰器和 stdlib 路径分派属于框架适配差异，不复制业务语义，因此不新增一层浅路由模块。
