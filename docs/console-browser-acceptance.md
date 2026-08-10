# Console 浏览器验收

本文档说明如何在本机重复执行 Console 的 Chrome CDP 烟测。烟测使用独立的临时 Chrome profile，不会接管、关闭或修改用户正在使用的 Chrome profile。

## 前置条件

先启动 Console 服务。仅验证结果面板可使用内存后端：

```powershell
.\scripts\start_console.ps1 -Mode memory -Port 8088
```

要验证真实武汉道路、水体和行政区几何，使用 GIS 环境及独立端口：

```powershell
.\scripts\start_console.ps1 -Mode gis -Port 8091
```

## 启动隔离 CDP

在另一个 PowerShell 窗口执行：

```powershell
.\scripts\console_cdp_start.ps1 -ConsoleUrl http://127.0.0.1:8088/
```

脚本默认监听 `127.0.0.1:9222`。如果该端口已经有 CDP，会先检查并复用，不会结束已有进程。首次启动会创建类似 `%TEMP%\spatial-agent-cdp-*` 的独立 profile。关闭该次验收 Chrome 后，临时 profile 可以手动删除。若使用其他端口，启动脚本和 smoke 脚本都设置相同的 `CDP_URL`：

```powershell
.\scripts\console_cdp_start.ps1 -Port 9333 -ConsoleUrl http://127.0.0.1:8088/
$env:CDP_URL = 'http://127.0.0.1:9333'
```

## 执行烟测

验证数据健康、会话恢复、清空工作区和建设筛选地图：

```powershell
node scripts/console_health_smoke.js
node scripts/console_session_smoke.js
node scripts/console_clear_smoke.js
$env:CONSOLE_URL = 'http://127.0.0.1:8091/'
$env:MAP_REQUEST = '分析洪山区建设适宜性，坡度不超过20度'
node scripts/console_map_smoke.js
```

验证空间总览专用面板和地图分层：

```powershell
$env:CONSOLE_URL = 'http://127.0.0.1:8088/'
$env:CONSOLE_BACKEND = 'memory'
node scripts/console_overview_smoke.js
```

该脚本先提交“分析洪山区空间概况”，断言 `spatial_overview_result` 对应的“空间总览摘要”显示工具步骤、数据来源和空间要素；随后使用固定的最小 GeoJSON 调用页面已有总览地图渲染函数，断言图层控制中存在“行政区边界”“道路”“水体”，且颜色分别为青绿色、橙色和蓝色。固定 GeoJSON 只验证前端分层契约，不替代真实 GIS 数据验收。

多个 smoke 脚本不要同时复用同一个 CDP 页面。它们都会选择第一个 page 并导航到
`CONSOLE_URL`，并行执行会互相覆盖页面状态，导致总览面板等断言偶发读取空结果；应使用
同一 CDP 实例串行执行，或为每个脚本提供独立页面/profile。

## M67 结果证据补充

结果区中的“结果证据”面板只在本次运行产生后显示，内容按响应动态生成，不代表每类问题都会固定显示栅格、健康检查或地图面板。验收时应分别确认：

- `result.geometry` 的状态、是否可绘制、要素数量、来源、CRS 和 GeoJSON 引用与实际响应一致；`no_geometry`、`unknown`（未知）和 `truncated_geometry` 必须明确显示为限制，不能当作真实空间形状。
- `runtime evidence` 显示运行时数据健康、GIS 依赖和能力快照状态；页面会优先使用响应内的 `runtime_evidence`，没有时通过现有 `/capabilities/runtime?max_files=3` 读取有界快照。
- `data evidence` 显示数据集的可用性、文件/要素数量、CRS 或覆盖范围；缺少数据质量证据时必须显示“不能据此推断数据已完成核验”。
- `provenance` 显示执行策略、工具步骤、状态和结果引用；澄清、拒绝或未执行工具的请求应明确显示没有工具血缘。
- “降级与限制”列出部分可用、不可用、失败步骤、数据警告、几何截断和仅摘要结果。正常结果也应保留“未发现明确降级状态”的边界说明。

静态契约由 `tests/test_m67_console_evidence.py` 验证。该测试只检查前端 DOM、渲染字段、现有接口路径和本验收说明，不替代真实 GIS、真实模型或浏览器运行验收。

若要通过真实 GIS 总览请求验证最终几何证据，将环境变量改为：

```powershell
$env:CONSOLE_URL = 'http://127.0.0.1:8091/'
$env:CONSOLE_BACKEND = 'local'
node scripts/console_overview_smoke.js
```

## 常见失败判定

- `无法连接 Chrome CDP`：先运行 `console_cdp_start.ps1`，或检查 `CDP_URL` 是否指向实际端口。
- “空间总览面板未显示”：检查服务是否返回终态，以及请求使用的 Planner/后端是否支持 `spatial_overview`。
- “地图缺少图层”：这是前端分层契约失败；真实数据缺少道路/水体时，仍应先用固定 GeoJSON 验证前端实现，再记录数据卷缺失。
- `console_map_smoke.js` 的真实几何失败：不能用内存后端替代，应确认已使用 `-Mode gis` 并挂载武汉数据。

这些 smoke 脚本不会把 Planner 成功、工具成功或 GeoJSON 引用存在误判为真实几何可绘制。
