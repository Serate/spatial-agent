# M326 阶段交接

## 状态

- 阶段：`M326` 开放式 ReAct 稳定交付
- 状态：已完成
- 交付范围：开放式增量动作、部分结果语义、答案投影、Artifact 原子发布、真实模型/GIS 和跨入口恢复验收
- 恢复入口：下一阶段优先读取 `docs/agent-work-state.md`、`tasks/current-state.md`、本文件和 M327 handoff；不读取本阶段完整源码或历史账本

## 已完成

- M326-A：开放 ReAct 使用独立策略投影，不再继承自动匹配 Domain 模板的步骤上限和工具白名单；
  Registry/schema、权限、审批、数据就绪、依赖、Domain 安全门禁和 Runtime 动作预算仍有效。
- M326-B/C：新增领域中立 `spatial-agent.result-completeness.v1`，统一 `complete`、`partial`、
  `blocked`、`waiting_decision`、`pending`，并将完成范围、动作计数、停止原因、可重试性和不确定性
  投影到 Result、evidence、轮询、SSE、Artifact、SQLite 恢复、Composite 和答案生成。
- M326-D：Artifact 使用同目录临时文件和原子替换发布；空结构化响应统一为
  `planning/invalid_model_response`；真实验收脚本要求 live model evidence 成功，不能把 fallback 当作真实模型成功。
- 真实模型 + Docker/GIS 已完成一次多步请求和一次矢量结果形态请求；多步请求真实执行 2/3 动作后安全收束为
  可重试 `partial`，未伪造未执行步骤。HTTP、异步、轮询、Artifact、Evidence、SSE 和重启恢复的核心 identity
  与完整性字段保持一致。

## 验证摘要

- Docker 阶段紧凑回归：`49/49` 通过。
- Artifact 原子写入与 Provider JSON 兼容/错误边界回归通过；compileall、architecture strict、readiness `200` 通过。
- `m308_cross_entry_acceptance.py` 的 sync/async/artifact/restart/evidence/view 对照通过。
- SSE 事件序号递增，`Last-Event-ID` 续传从下一事件开始；真实 GIS 容器只读挂载 `D:\dataset\agent`，验收结束后已清理。
- 未提交真实数据、API key、Prompt、模型原文、完整私有结果或临时输出。

## 已知问题与边界

- DeepSeek/兼容 Provider 的结构化响应质量依赖输出预算和 wire 能力；Planner 继续在本地执行有界 JSON 解析与契约校验。
- 默认离线测试不访问网络、不依赖私有数据；真实模型、真实 GIS、Docker 和浏览器只通过显式验收路径运行。
- `partial` 不是完整分析结论；答案必须说明已完成事实、未完成范围和是否可重试。

## 下一阶段

- M327 聚焦“开放请求的能力发现与结果质量”：完善能力目录的可组合描述、动态结果摘要和用户可解释的执行选择，
  保持 Runtime/Domain 边界，不为区域或固定问句增加分支。
- M327 的详细入口见 `docs/stages/M327/`；阶段循环仍为全局规划 → Spec → Plan → 实现 → 最小验证 → 交接 → 重规划 → 提交推送。
