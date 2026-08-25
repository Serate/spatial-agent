# M284 会话清空与跨入口状态一致性能力图

## 阶段目标

修复 M283-D/E 暴露的前端状态一致性缺口：清空会话、切换会话或切换领域后，旧的空间选择、地图实例、结果 projection 和异步渲染不能继续滞留或回写。

本阶段只治理 Console 的公共 reset/lifecycle seam，不修改 Agent Runtime、Planner、ToolRegistry、GIS 算法、Result Contract 或服务端持久化语义。

## 能力分层

| 模块 ID | 责任 | 依赖 | 不负责 |
|---|---|---|---|
| `reset-boundary` | 为 RendererRegistry 和 adapter 定义可观察、可复用的 workspace reset 输入与 surface 清理责任 | renderer registry、surface targets | 领域业务语义、服务端数据删除 |
| `stale-render-guard` | 在 clear/session/domain 变化后使旧的异步 render、history restore 和 evidence hydration 失效 | conversation/domain generation、reset boundary | 重新执行请求、修改 SQLite |
| `reset-acceptance` | 用精简 Node contract 和串行 browser regression 验证 selection、map、projection、结果工作区一致清空 | 前两个模块、现有 map smoke | 默认 CI 联网、真实模型调用 |

## 构建顺序

`reset-boundary` → `stale-render-guard` → `reset-acceptance`

## 七维度全局依据

1. 产品：清空对话必须让用户看到真正的空白工作区，不能保留上一轮空间上下文。
2. 架构：reset 是公共 renderer lifecycle seam；GIS 只负责自身地图和 selection 的清理，不把 GIS 判断放进 Console 主流程。
3. 数据：清空 UI 不伪造服务端删除成功；持久化 clear 失败仍以结构化错误提示，前端 workspace 先安全清空。
4. 模型：旧请求或 evidence hydration 不能在清空后重新写入结果；不新增模型调用。
5. 部署：FastAPI/stdlib/静态资源边界不变；Docker 只用于显式验证。
6. 体验：selection、地图、答案、projection、advanced details 和按钮状态必须回到同一空态；支持 reduced-motion 和键盘操作现有约束。
7. 测试：保留一条 reset contract、一条串行 browser regression；失败时区分 reset、异步竞态和服务端 clear 三类原因。

## 不做事项

- 不为 GIS 地图增加新的页面分支或固定区域判断。
- 不修改会话数据库 schema、artifact、Runtime lifecycle 或 HTTP 语义。
- 不通过延时等待掩盖旧 render；必须使用 generation/reset contract 使其失效。
- 不把地图 smoke 的失败改成宽松断言。
