# M302 分阶段 Planner 上下文与开放问题成功链路能力图

## 全局定位

M301 已解决“无关 Domain 缺失事实过早阻断 Planner”和“内部 Context 与模型预算混用”问题。M302 从项目整体继续提升开放式请求的真实成功率：让 Planner 在不同生命周期阶段只接收完成当前决策所需的上下文，并让选定能力稳定进入 TaskPlan、执行、答案和证据闭环。

本阶段不新增专题硬编码、不引入 RAG、不扩大工具菜单；重点是让已有能力更像一个真正可用的通用 Agent。

## 能力切片

| 切片 | 目标 | 交付证据 |
| --- | --- | --- |
| stage-aware envelope | 按 discovery、selection、execution、repair 阶段投影最小模型上下文 | 同一公共 Envelope 契约与预算测量 |
| planner selection closure | 让模型从可用候选中选择一个或多个能力，选择后保留 identity/readiness | Planner → TaskPlan → binding 对照 |
| selected-fact continuation | 选定组件缺事实时只请求必要字段，补充后稳定续跑 | continuation fingerprint 与不创建错误 run |
| answer/result synthesis | 用结构化结果生成简洁、非程序化的回答，事实不可被模型改写 | Result/Evidence 引用一致 |
| live cross-domain acceptance | Docker + 真实模型 + 真实 GIS/Economic 数据完成成功、澄清、provider failure 三类验收 | 脱敏 live receipt |
| delivery and global review | 更新中文记忆、版本、部署说明并从七维度重规划 | 阶段提交、推送和下一阶段计划 |

## 当前推进位置

- M302-A/B 已完成阶段投影的公共边界；M302-C 已完成 validated binding 驱动的 execution projection identity 闭合。
- 下一片为 M302-D：从项目全局检查结构化结果、答案生成、evidence 和前端 View 是否消费同一事实来源；优先压缩程序化摘要和重复展示，不把答案模型变成第二个执行器。

## 七维度约束

- 产品：用户只看到与当前问题相关的 Agent 阶段、简洁结果和必要澄清。
- 架构：阶段投影是公共 Runtime seam；Domain 只提供事实、能力和工作流声明。
- 数据：数据 readiness、事实缺失和结果证据分离，不用扩大上下文掩盖数据缺口。
- 模型：模型只能选择目录中的候选，不能发明工具、数据或数值；模型失败可重试但不伪装成功。
- 部署：生产入口保持 `openai + local`；Docker 是默认 Python/GIS 验证环境，live 仍显式执行。
- 体验：前端消费结构化 View/Evidence，不展示内部 envelope、工具名、prompt 或思维链。
- 测试：按独立失败模式合并为少量阶段门禁，避免每个小改动重复测试。

## 不在本阶段范围

- 不为某个区域、问句或数据集增加分支。
- 不直接放宽 ToolRegistry、TaskPlan、workflow 或 execution binding 门禁。
- 不保存模型原文、密钥、私有路径或完整原始数据。
