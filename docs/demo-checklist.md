# Spatial Agent 演示验收清单

## 离线演示

```powershell
scripts\start_console.ps1 -Mode memory -Port 8088
```

打开 `http://127.0.0.1:8088/`，选择“规则规划器 / 内存演示”，依次验证：

- `查询DEM栅格元数据`
- `分析DEM高程统计`
- `查询洪山区行政区边界`
- `查询洪山区行政区边界并分析DEM高程概况`

重点观察任务步骤、依赖、运行血缘、统计概览和执行轨迹。

## 真实 GIS 演示

```powershell
scripts\start_console.ps1 -Mode gis -Port 8088
```

选择“规则规划器 / 本地 GIS”，验证：

- `分析洪山区DEM高程概况`
- `分析洪山区土地利用分布`
- `查询洪山区行政区边界并分析DEM高程概况`

预期 DEM 区域均值约为 `26.533`，有效像元约为 `576016`；实际值以本地数据为准。

## 真实模型演示

在允许出站网络的服务进程中选择“真实大模型 / 本地 GIS”，使用同一个复合请求：

```text
查询洪山区行政区边界并分析DEM高程概况
```

真实模型演示会消耗 Token，默认离线测试不会调用模型。

## 自动化回归

```powershell
python -m unittest discover -s tests
python scripts\smoke_check.py
python scripts\evaluate_planner.py --planner rule --backend memory
```

核心流程整体验收：

```powershell
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' -m unittest tests.test_m44_core_workflows
& 'C:\Users\torch\AppData\Local\Programs\Python\Python314\python.exe' scripts\evaluate_planner.py --planner rule --backend memory --cases evaluation/cases/core-workflows.json --strict
```

## 失败恢复演示

使用 API：

```text
POST /runs/{run_id}/retry
POST /runs/{run_id}/cancel
```

失败 Run 可从第一个失败步骤恢复；取消和超时会保留已完成步骤，并将后续步骤标记为阻塞。
