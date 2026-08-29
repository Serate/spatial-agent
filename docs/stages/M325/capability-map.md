# M325 能力图：真实模型与 Docker/GIS 纵向验收

## 全局目的

M324 已完成工具提案的人工审批、持久化、Registry 治理和控制台可见化。M325 不再新增一套
专题流程，而是把已有 Runtime 能力放到真实运行边界中验证：真实模型负责开放式决策，ReAct
负责多步工具组合，GIS 使用 Docker 挂载的本地数据，网络搜索只经过白名单适配器，最终结果
通过 HTTP、artifact、恢复和前端共同契约交付。

## 能力分层

| 模块 | 责任 | 已有 canonical seam | M325 验收重点 |
|---|---|---|---|
| provider | 读取本地配置、调用兼容 Chat Completions、记录安全模型证据 | `agent/integration/`、`agent/llm_planner.py` | 连接、结构化计划、超时和非法响应分类 |
| ReAct | 按轮次决定工具、搜索、澄清或完成，并限制预算和重复动作 | `agent/react/`、`agent/runtime_core/react_runtime.py` | 至少两步真实决策或明确可审计降级 |
| GIS Domain | 从受控数据目录发现、执行和投影空间结果 | `domains/gis/`、`domains/gis/adapters/` | Docker + local backend 的真实数据健康与结果 |
| web search | 只访问服务器配置的 HTTPS 白名单，返回 bounded document evidence | `agent/network/web_search.py` | 白名单成功、越界拒绝、无配置降级 |
| governance | 动态 Python 提案必须审批后才能绑定和执行 | `agent/tooling/approval.py`、`rehydration.py` | pending 不执行，approved 可恢复，失配 fail closed |
| delivery | 事件、答案流、结构化结果、地图、证据和 artifact 一致 | `agent/run_events.py`、HTTP/Application、Console | 复杂请求完成、失败可解释、入口结果一致 |

## 纵向路径

```text
自然语言请求
  → 真实模型结构化 ReAct 决策
  → 能力/数据目录与 Execution Policy 校验
  → ToolRegistry 分发
      ├─ Docker GIS 本地数据
      ├─ 白名单公共网页搜索
      └─ 已审批动态工具（如存在）
  → Result / Evidence / Artifact
  → SSE/轮询/前端/重启恢复
```

## 边界

- 不允许模型直接提供 URL、HTTP 方法、请求头、脚本或未注册工具。
- 不从模型输出或持久化记录读取并执行源码；未审批提案只停留在治理状态。
- 默认离线 CI 不访问网络、不依赖私有数据；真实模型和网络只通过显式命令验收。
- 真实数据缺失、模型超时、搜索未配置或 GIS 依赖不可用时，必须返回结构化降级原因，不能
  伪装成成功。
