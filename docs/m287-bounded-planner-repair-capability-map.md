# M287 有界 Planner 修复与失败恢复能力图

## 阶段定位

M286 已确认：真实中转可以到达 Planner，但仍可能返回未声明组件字段。公共 schema 和 allowlist 不能因此放宽；下一步应让 Agent 在可恢复的 schema 失败上进行一次受控修复，再次经过完全相同的 canonical plan/TaskPlan 门控。

M287 仍是通用 Runtime 能力，不为 GIS、Economic 或某个 provider 增加专用流程。模型只能修复自己的结构化输出，不能修复事实、权限、数据健康或工具结果。

## 全局缺口

| 维度 | 当前能力 | M287 目标 |
| --- | --- | --- |
| 产品 | 失败可读但常停在拒绝 | 可区分可修复 schema 失败与不可修复能力/数据失败 |
| 架构 | Application 有 `repair_planner` seam，但生产适配不足 | 统一 Repair Request、一次重试和 repair lineage |
| 数据 | 数据 readiness 已进入 context | 修复不改变数据选择、权限或事实 |
| 模型 | provider 输出偶发字段漂移 | 用有限错误类别反馈严格 schema，不暴露原文 |
| 部署 | live harness 有 deadline/0 retry | repair 总预算受单次 run deadline 和一次 retry 限制 |
| 体验 | 前端可展示 planner evidence | 动态显示“正在校正计划/校正失败/需人工补充” |
| 测试 | replay/跨入口 fail-closed 已有 | 少量修复成功、修复失败和禁止修复场景 |

## 完整任务包

1. 冻结 Repair Request/Lineage 版本化结构和可修复错误码白名单。
2. 实现 provider-neutral repair adapter，复用原 context 和 schema，不保存原始响应。
3. 接入 Composite Planning Application、HTTP、async、artifact/restart 和前端 projection。
4. 验证重试次数、deadline、幂等、未知能力/数据失败不重试，以及结果/evidence 一致性。
5. 用脱敏 replay 固化，Docker 阶段收口后只做一次真实中转修复验收。

## 不做

- 不接受未知字段或未知 capability。
- 不把模型修复变成事实补全、自由工具发现或外部搜索。
- 不增加默认 CI 的网络调用，不保存 prompt、模型原文、key 或私有路径。
