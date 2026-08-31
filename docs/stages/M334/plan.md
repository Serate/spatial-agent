# Plan：M334 多来源证据与跨域组合

> 单 Agent，最大并发度 1；一个子任务覆盖完整能力链的一组实现，开发中只做必要检查，阶段收口统一验证。

## M334-0：阶段初始化与契约冻结 — 已完成

- [x] 将 M334 设为 active stage，更新热状态、短账本和文档索引。
- [x] 固定 Evidence Source、Quality、Bundle 和 Composite 的版本字段、敏感字段边界和迁移规则。
- [x] 从现有 `document_evidence`、GIS Result 和 `agent/evidence/` 选择兼容投影，不复制已有 registry。
- 验证：`pwsh -NoProfile -File scripts/validate_document_index.ps1` 通过；未运行业务测试。

## M334-A：来源身份与质量深模块

- [x] 实现来源定位规范化、稳定 source id、内容指纹和重复判定。
- [x] 实现固定时钟下的 freshness/completeness/status 计算，缺失时间保持 unknown。
- [x] 将质量 receipt 接入现有 Evidence projection，保持历史 payload 可读取。
- [x] 增加敏感字段剥离和数量上限。
- 验证：M334 identity/quality 紧凑契约已覆盖并通过。

## M334-B：多来源 Bundle 与跨入口投影

- [x] 聚合 Web Search/Fetch、GIS 和指标结果的安全来源 entry。
- [x] 稳定去重、排序、duplicate lineage、coverage 和 limitations。
- [x] 让答案上下文、SQLite、Artifact、RunEvent、HTTP/SSE 只消费 bundle 安全投影。
- 验证：Bundle、Composite、Result Summary 和跨入口 Evidence projection 已接入。

## M334-C：跨域 Composite 事实组合

- [x] 在通用 Composite View 中增加事实到来源的显式引用和数据范围/时间范围元数据。
- [x] 发现无法对齐的 CRS、时间、单位、范围或版本时保留 limitation，不进行隐式拼接。
- [x] 让 Composite 结果把来源缺口、对齐状态和事实 receipt 交给后续答案/Runtime 决策层。
- 验证：网页 + 本地 GIS fake results 的跨域组合契约；未新增专题规则。

## M334-D：答案质量、降级与恢复

- [x] 重写答案上下文投影，使模型看到来源质量、覆盖和限制，而不是内部 registry 细节。
- [x] 网络失败、过期、冲突和局部成功时生成结构化可读降级；保持答案流和已有直接回答。
- [x] 验证同一 bundle 在同步、异步、恢复、Artifact、SSE 和前端结果层的一致性（Docker 收口验收仍在 E）。

## M334-E：Docker/真实模型验收与阶段交付

- [x] 使用 Docker 验证编译、架构、readiness、SQLite/Artifact 和真实 GIS 数据链路。
- [x] 显式执行一次真实模型 + 本地 GIS + 受控公共网页的多来源请求；只记录脱敏状态、数量、来源域名和 reason codes。
- [x] 更新中文问题日志、模块职责索引、代码/文档索引和 handoff，提交并推送版本。
- [x] 基于产品、Runtime、Planner、Domain/数据、部署和测试全局重规划下一阶段。

### M334-E 实际验收记录

- Docker `quick + stage + smoke` 通过；核心回归 `56/56` 通过；`compileall`、`architecture_check.py --strict` 和 `/health/ready` HTTP `200` 通过。
- 生产 acceptance 通过：liveness/readiness、通用能力目录、GIS 数据卷、preview、同步/Artifact、失败契约、异步恢复与幂等均通过；根 Host 与 GIS Domain 快照采用各自正确的能力/数据证据平面。
- 真实模型 + 本地 GIS + `public` 网页显式验收实际执行 3 个工具步骤，但 Provider 在有界预算内未完成；结果按 `provider_timeout`/网络不可用安全降级处理，未伪造网页来源，未保存模型原文、Prompt、网页正文或密钥。
- acceptance 兼容性修复：支持通用 `capability_descriptors`、合法空工具策略和可重复的唯一会话；修复不改变 Runtime 公共契约。

## 阶段门禁

- 文档索引校验。
- M334 紧凑契约测试及受影响的 Composite/答案测试。
- `python -m compileall -q agent domains scripts`。
- `python scripts/architecture_check.py --strict`。
- Docker readiness、持久化/恢复和一次显式真实验收。

## 风险与回退

- 旧 Evidence 无时间字段：迁移为 `unknown`，不阻断历史结果读取。
- 不同来源内容冲突：并列来源并显示 limitation，不自动选“更可信”的一个。
- 来源数量或上下文过大：按稳定优先级截断并记录 coverage/omitted count。
- 网络不可用：只标记网络来源 unavailable，保留本地/直接回答路径。
