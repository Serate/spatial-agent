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
