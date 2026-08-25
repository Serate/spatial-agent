# Spec: M284 会话清空与跨入口状态一致性

## Objective

为 Agent Console 建立领域中立的 workspace reset 契约。用户点击“清空对话”、切换会话或切换领域后，前端必须同步清除旧的结果工作区、地图实例、地图选择上下文、projection 和高级详情；任何已开始但尚未完成的异步渲染或历史恢复不得把旧状态写回。

### 当前假设

1. 服务端 session clear 仍是持久化事实来源；本阶段只修复客户端 workspace 生命周期。
2. 桌面 Web 是主验收平台，现有键盘焦点和 reduced-motion 规则继续有效。
3. RendererRegistry 是所有可视化 adapter 的公共生命周期入口；GIS adapter 只清理自己的地图和选择状态。
4. 不引入第三方依赖，不改变 Result/View/Evidence schema。

## Commands

源码/契约：

```text
node scripts/console_reset_contract_smoke.js
node --check web/src/console_renderer_registry.js
node --check web/src/console_gis_plugin.js
node --check web/src/console_app.js
```

Docker：

```text
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build spatial-agent
docker exec ai-agent-spatial-agent-1 micromamba run -n spatial-agent-gis python -m compileall -q agent production_api.py serve_api.py
docker exec ai-agent-spatial-agent-1 micromamba run -n spatial-agent-gis python scripts/architecture_check.py --strict
```

浏览器：

```text
node scripts/console_map_smoke.js
```

浏览器 smoke 必须串行使用单个 CDP 页面，不与其它 smoke 并行导航。

## Project Structure

| 文件 | 责任 |
|---|---|
| `web/src/console_renderer_registry.js` | 公共 adapter reset、generation 失效和 surface 生命周期 |
| `web/src/console_gis_plugin.js` | 地图实例、图层和空间 selection 的 adapter-owned 清理 |
| `web/src/console_app.js` | 会话/领域变化触发 reset，维护 conversation/domain generation |
| `scripts/console_reset_contract_smoke.js` | Node-only reset 和 stale-render contract |
| `scripts/console_map_smoke.js` | 真实浏览器地图、选择和清空回归 |

## Contract

Renderer adapter 的 `reset(context)` 接收有界 context：

```js
{
  reason: "clear-session" | "switch-session" | "switch-domain" | "new-run",
  generation: Number,
  surfaces: {generic: HTMLElementLike, visual: HTMLElementLike}
}
```

Registry 必须先使正在进行的 render 失效，再通知所有已注册 adapter。Adapter 必须清理自己创建的 surface 内容和内部 selection/context；未知 adapter 仍使用安全的 generic 行为。清理操作必须同步完成，不依赖网络或固定延时。

## User-visible behavior

- 清空后：结果区显示空态；答案、projection、地图、selection、选择按钮、DAG、trace 和 evidence 为空或隐藏。
- 清空后：`rendererRegistry.context()` 不包含上一轮的空间选择。
- 清空请求返回失败时：workspace 仍保持清空，并显示持久化清理失败提示，不恢复旧结果。
- 清空后：旧的异步 map/render/evidence 结果即使随后完成，也不能写回当前 workspace。
- 切换会话或领域：与清空对话使用相同 reset boundary，不复制一套清理逻辑。

## Testing Strategy

- Node contract：用 fake surface/adapter 验证 reset 通知、surface 清理和 stale render superseded；不启动 HTTP、GIS、浏览器或模型。
- Browser regression：复用现有地图 smoke，验证真实 Leaflet/selection → clear → immediate empty → delayed empty；失败要输出 selection、context、map 和 result 状态。
- Docker：只执行 compile/import、architecture strict 和显式浏览器服务验证；不把 live 模型加入默认 CI。

## Boundaries

- Always：通过 Registry reset seam 清理；保留 generation guard；保留服务端 clear 错误提示；使用精简、可重复测试。
- Ask first：改变服务端会话删除语义、数据库 schema、公共 View schema 或引入新前端依赖。
- Never：在 `console_app.js` 增加 GIS 专用清理分支；用 `setTimeout` 作为一致性保障；删除或放宽失败 smoke；提交密钥或模型原文。

## Success Criteria

1. Node reset contract 通过，能证明 registry reset 会使旧 render 失效并清理 surfaces。
2. `console_map_smoke.js` 通过：清空后立即和等待 1 秒后均无 Leaflet/map SVG、selection context、启用的 selection button 或旧结果。
3. Docker compileall、architecture strict、readiness 通过；现有 M283 projection smoke 不回归。
4. reset 代码不包含 GIS/区域/工具名专用判断，且不修改 Runtime、Planner、ToolRegistry 和 Result schema。
5. 清理失败时不恢复旧 workspace，仍显示结构化持久化错误。

## Open Questions

- 是否在后续阶段把服务端 clear 与前端 reset 统一为显式 interaction receipt？M284 不扩展该边界，先保持现有 HTTP 语义。
