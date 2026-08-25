# M292 Planner 组件事实交接与可恢复澄清 Spec

## 目标

建立 `spatial-agent.component-fact-handoff.v1`，让每个已选组件声明其公共必需事实、当前已知事实、缺失字段和可继续动作。澄清必须能沿用原始 request fingerprint 和组件身份，补充后重新经过同一 Planner/TaskPlan gate。

## 公共契约

1. handoff 只允许版本化的实体、数据集、约束、时间范围和输出偏好摘要；禁止 prompt、模型原文、私有路径、凭据和未经声明的 Domain 私有字段。
2. 每个缺失事实包含 `component_id`、`domain_id`、`capability_id`、字段名、用户可读标签、来源（request/catalog/workflow/user）和是否必填。
3. 澄清结果包含原 request fingerprint、planner selection fingerprint、组件列表摘要和 continuation token；不能重新生成一个无关联的新请求。
4. 补充事实后，Runtime 必须重新执行 context → plan → completeness → TaskPlan gate；不得直接拼接旧计划绕过校验。
5. sync、async、HTTP、前端、artifact 和 restart 恢复对同一澄清 continuation 返回一致的状态与 evidence。
6. 缺失数据集或后端不可用仍使用既有 recoverable unavailable 语义，不伪装为用户事实缺失。

## 验收

- replay 覆盖单组件缺事实、多组件部分缺事实、用户补充后成功、补充后仍缺失、fingerprint 不匹配和未知字段拒绝。
- 组件级澄清能在 HTTP/前端显示最小必要信息，并保留原能力选择和来源证据。
- 未完成澄清不创建 execution run；继续执行只复用同一生命周期入口。
- Docker 阶段收口执行一组精简 continuation contract、compileall、architecture/readiness 和一次显式 live（若 provider 可用）。
