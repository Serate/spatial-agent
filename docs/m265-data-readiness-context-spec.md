# M265 数据就绪事实进入 Planner Context Spec

状态：已完成

## Objective

让 LLM Planner 和规则 Planner 在选择能力时看到当前数据目录的有界事实：数据是否 ready、覆盖范围、时间范围、CRS、分辨率、stage、可用性原因以及 DEM/土地利用等派生数据的对齐状态。

这一步服务于 GIS、Economic 和未来专题的共同规划边界；它不把数据目录变成执行授权，也不把文件系统、私有路径或完整健康报告塞进模型上下文。

## Public contract

在 Planner-facing `capability_catalog` projection 中，为选中能力增加：

```json
{
  "dataset_evidence": {
    "dem": {
      "status": "ready",
      "coverage": [756630, 3318720, 893490, 3477030],
      "time_range": null,
      "crs": ["EPSG:32649"],
      "resolution": [30, 30],
      "stage": "analysis-ready",
      "availability_reason": null,
      "analysis_ready": {"status": "ready", "grid_alignment": "aligned"}
    }
  }
}
```

字段必须有界、可序列化；不包含绝对文件路径、原始异常、完整 GeoJSON、密钥或模型原文。旧 Domain/旧 snapshot 缺少该字段时使用空对象，不改变既有计划。

## Integration rules

1. `DatasetCatalog` 的 discovery metadata 进入 GIS runtime `data_evidence`，但只保留公共字段。
2. `capability_context_summary()` 只为选中/投影的能力携带其声明 datasets 的 evidence，避免扩大 token。
3. `planner_context.py` 传播 `dataset_evidence`；同步、异步、artifact 和最终 Result 继续保存原有完整 evidence，不复制另一套业务结果。
4. 执行前的 CRS、栅格对齐、数据缺失和权限 gate 仍由 Domain/ToolRegistry 执行；模型只能依据事实规划已注册工具。
5. Economic 等非 GIS Domain 可以提供相同形状的 `time_range/source` 摘要，但本阶段没有经济专用分支。

## Commands

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml build spatial-agent
docker compose --env-file .env.production -f docker-compose.prod.yml up -d spatial-agent
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m265_data_readiness_context -v
docker exec ai-agent-spatial-agent-1 python -m unittest tests.test_m249_open_planner tests.test_m251_indicators tests.test_m263_economic_domain -v
docker exec ai-agent-spatial-agent-1 python -m compileall -q agent domains scripts tests
docker exec ai-agent-spatial-agent-1 python scripts/architecture_check.py --strict
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile quick
docker exec ai-agent-spatial-agent-1 python scripts/test_profile.py --profile stage
```

## Project structure

```text
agent/runtime_capabilities.py       # 目录 discovery → bounded data_evidence
agent/capability_catalog.py         # capability → dataset_evidence projection
agent/planner_context.py             # Planner section propagation
tests/test_m265_data_readiness_context.py
```

## Testing strategy

- projection contract：合成目录事实验证字段白名单、截断和选中能力过滤。
- Planner context：验证选中 GIS capability 能看到数据就绪事实，未选中能力的数据不进入上下文。
- backward compatibility：旧 snapshot/无 discovery、Text、Indicators 和 Economic 仍能生成合法 context。
- Docker：默认精简离线回归；真实 GIS/Docker 只显式验收，不进入 CI。

## Boundaries

- Always：只投影目录元数据；有界；保留数据状态和失败原因；执行门禁不后移。
- Ask first：修改 Result Contract、改变 capability selection 状态、引入新的数据发现服务或外部依赖。
- Never：向模型提供绝对路径、原始栅格/矢量、私有配置、未经验证的覆盖结论；不在 Runtime 写 GIS 专用策略。

## Success criteria

1. Planner context 的选中能力包含所需 dataset evidence，且大小受预算控制。
2. coverage/time_range/CRS/resolution/alignment 缺失时以 `null/unknown/空对象` 表示，不猜测。
3. 现有执行 gate、Result、artifact、SQLite/restart 语义不改变。
4. GIS、Economic、Indicators 和 Text 回归通过，公共 Runtime 不增加领域分支。
5. Docker M265 定向、compileall、architecture strict 和 quick/stage 通过。

## Completion evidence

- Docker M265 与 M249/M251/M263 定向回归 **14/14** 通过。
- Docker `stage`、`quick`、`compileall` 和 `architecture_check.py --strict` 全部通过。
- 真实 GIS capability snapshot 为 `environment=local`、`health_status=ready`；选中建设能力的 Planner projection 仅包含 `admin_areas`、`dem`、`land_use` 的 bounded evidence，包含 coverage/CRS/analysis-ready 对齐状态，不包含路径。
- 容器内 M265 相关源码与工作区 SHA-256 一致；未改变 Result、artifact、SQLite/restart 或执行 gate。
