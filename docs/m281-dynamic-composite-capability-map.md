# M281 动态 Composite 结果体验能力图

## 阶段目标

把 M280 已稳定的 Composite Result、View、Evidence 和生命周期真正传到用户体验：用户问一句开放式问题后，看到简洁结论、按数据形态组织的结果、地图/指标/趋势/来源和可展开的执行证据；CLI、HTTP、前端与 artifact 使用同一核心投影。

```text
Composite Result + Evidence
  -> domain-neutral View Projection
  -> concise Answer Contract
  -> CLI / HTTP / artifact
  -> generic frontend renderer
  -> browser and cross-entry acceptance
```

## 全局盘点

| 维度 | M280 后状态 | M281 缺口 |
|---|---|---|
| 产品 | Composite 可执行、可恢复 | 结论层级不够清晰，用户仍可能看到程序化细节 |
| 架构 | Runtime/Coordinator/Result/Evidence 已分离 | 缺少统一的用户 View Projection seam |
| 模型 | 真实 Planner 可达但输出不稳定 | 合法计划的答案必须基于 canonical facts，不依赖原文 |
| 数据/GIS | vector/raster/metrics/timeseries 契约已存在 | 多种数据形态需统一展示语义和降级说明 |
| 入口 | HTTP/async/artifact/restart 结果一致 | CLI、HTTP、前端需要验证同一 projection/fingerprint |
| 部署 | Docker 真实跨域验收通过 | 浏览器验收需在生产镜像中消费动态 payload |
| 测试 | 离线契约与显式 live 分层 | 增加少量跨入口/browser smoke，不扩大默认 CI |

## 不变量

- 前端按 `data_profile`、View 类型和结构化 evidence 渲染，不判断 `gis`、`economic`、洪山区或工具名称。
- 简洁答案只能来自 canonical Result/证据投影；模型原文、prompt、密钥和私有路径永不进入公共 payload。
- 部分结果、失败、澄清、数据不可用和空态都必须有明确可读状态，不用空白面板伪装成功。
- 新增一种结果形态优先扩展 Result/View Registry 和通用 renderer，不复制 Composite/Runtime 生命周期。

## 阶段分层

1. **公共投影**：定义版本化 `Composite View Projection`，稳定映射结果、子结果、证据和 artifact。
2. **答案边界**：定义简洁、可读、可降级的结构化答案，不暴露内部推理。
3. **前端消费**：generic renderer 支持 vector、raster、metrics、timeseries、document_evidence、composite 及 partial/error。
4. **跨入口验收**：CLI/HTTP/前端/artifact 比较核心 fingerprint、答案摘要、View 类型和 evidence 引用。
