# M334 能力地图：多来源证据与跨域组合

## 目标

把 M333 的“可受控读取网页”提升为可组合的证据能力：多个网页、GIS、指标或文本结果能够以统一身份、时间、新鲜度和完整性被汇总，供 Planner、Runtime 和答案生成共同消费。网络失败、来源重复、来源过期或不同领域结果无法对齐时，系统必须给出结构化限制，而不是伪造完整结论。

## 能力模块

| 模块 | 职责 | 依赖 | 交付边界 |
|---|---|---|---|
| `evidence-identity` | 规范化来源身份、版本、时间和内容指纹 | Evidence contract | 相同来源可去重；来源元数据安全且可恢复 |
| `evidence-quality` | 计算新鲜度、完整性、可用性和质量状态 | `evidence-identity` | 统一 quality receipt；不把模型判断伪装成数据事实 |
| `evidence-bundle` | 聚合有界的多来源证据并建立覆盖关系 | `evidence-quality`、Web/GIS results | 统一排序、去重、来源上限和缺口说明 |
| `cross-domain-composite` | 将多个 Domain Result 组合为领域无关 Composite | Result Registry、`evidence-bundle` | 事实、指标、矢量、栅格和文档证据共享 provenance |
| `quality-integration` | 接入答案、恢复、HTTP/SSE、Artifact 和前端投影 | 前四模块 | 展示来源质量与限制；不增加领域专用页面分支 |

## 构建顺序

`evidence-identity` → `evidence-quality` → `evidence-bundle` → `cross-domain-composite` → `quality-integration`

## 全局价值

- 产品：回答“最近”“比较”“综合分析”等问题时，用户能看到来源范围、时间和限制。
- Runtime：来源质量是统一执行事实，不由某个 Domain 或答案模板私自解释。
- Planner：可以根据来源缺口决定继续搜索、请求澄清、降级回答或拒绝高风险结论。
- Domain：GIS、经济、文本等只提供结构化结果，不承担跨域证据编排。
- 部署：网络不可用只影响网络证据，不破坏不依赖网络的直接回答和已有本地结果。
