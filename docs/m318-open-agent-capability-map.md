# M318-M325 开放 Agent 能力地图

## 定位

本 initiative 在已有 Runtime、RunEvent、SSE、答案流、Result、Evidence 和 Domain Pack
基础上，增加受控的全量 ReAct、通用执行策略、白名单网络搜索、Python 工具提案和人工审批。
GIS 仍是业务载体，不为每个专题复制一条 Runtime 生命周期。

## 能力模块

| 模块 id | 职责 | 依赖 |
|---|---|---|
| execution-policy | 在 direct tool、通用 DAG、Domain workflow、ReAct 间选择执行策略 | Capability Catalog、ToolRegistry |
| react-loop | 逐轮决策、结果引用、停止、澄清、修复和恢复 | execution-policy、RunEvent |
| web-evidence | 搜索、公共网页抓取、来源和引用 | ToolRegistry、Result Contract |
| tool-factory | Python 工具提案、静态检查和 Docker 沙箱 | Artifact、ToolRegistry |
| approval-governance | 人工审批、持久化、注册、版本和撤销 | SQLite、tool-factory |
| surface-integration | CLI、HTTP、SSE、前端和恢复统一消费 | RunEvent、Result、Evidence |
| acceptance | Docker、真实模型、真实 GIS、搜索、浏览器和跨入口验收 | 全部模块 |

## 建设顺序

`execution-policy → react-loop → web-evidence → tool-factory → approval-governance`

`surface-integration` 贯穿各阶段，`acceptance` 在每个阶段收口并于 M325 完成完整验收。

## 固定决策

- 真实模型默认使用 full ReAct；简单请求允许第一轮直接结束。
- 网络搜索默认开启，但只能访问部署配置的公共网页白名单。
- 工具提案默认开启，但只能生成沙箱 Python，必须人工确认后注册。
- 默认 CI 通过环境变量关闭网络和工具提案；不保存密钥、Prompt、模型原文或隐藏思维链。
- 单 Agent 顺序开发，最大并发度为 1；Python、GIS 和验收统一在 Docker 中运行。
