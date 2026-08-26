# Spec：M303 开放式 LLM Composite 执行成功链路

## Objective

让真实 LLM Planner 能够根据阶段化 Planner Envelope、能力目录、数据 readiness 和工具/结果契约，把一个开放式跨领域请求转换为已注册能力组成的合法 Composite TaskPlan/DAG，并复用现有生命周期进入真实 GIS/Economic 执行、答案、证据和 artifact 链路。

用户不需要知道内部组件 ID、workflow 或 binding；系统必须把模型的不确定性映射为可读澄清、结构化拒绝、可重试 provider failure 或真实执行结果。模型不能创建能力、数据、几何或统计事实。

## Assumptions

1. 当前产品入口默认使用 `openai + local`，Docker 已具备 GIS 依赖和已挂载数据目录。
2. Provider 使用已有 OpenAI-compatible structured-output client；本阶段不更换 provider SDK 或增加无界重试。
3. GIS 与 Economic Domain Pack 已有可执行能力、workflow、Result/View/Evidence 声明；本阶段只改善它们被模型组合和验收的路径。
4. 默认测试仍离线；真实模型和真实数据只在显式验收命令中执行。
5. 真实中转延迟和语义输出不稳定是外部变量，必须通过脱敏 receipt 分类，不得伪装成业务成功。

## Tech Stack

- Python 3.11，现有 Agent Runtime、Composite Planner、ToolRegistry、TaskPlan/DAG 和生命周期实现。
- Docker Compose 生产同构镜像，包含 GDAL/PROJ/Rasterio/GeoPandas/Node.js。
- Python `unittest` 精简契约；Node projection smoke；PowerShell HTTP acceptance。
- OpenAI-compatible JSON structured output，仅使用现有 provider configuration 和显式 live 开关。

## Commands

以下命令均从项目根目录执行；Python、GIS 和 compileall 必须在 Docker 中运行。

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production build spatial-agent
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m unittest tests.test_m303_open_composite_execution -v
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python scripts/architecture_check.py --strict
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent python -m compileall -q agent scripts tests
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps spatial-agent node scripts/console_result_projection_smoke.js
& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoProfile -File scripts/production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps -e SPATIAL_AGENT_LIVE_OPENAI=1 -e SPATIAL_AGENT_LIVE_GIS=1 spatial-agent python scripts/live_provider_probe.py --allow-network --composite --backend local --domains gis,economic --timeout-seconds 60 --max-output-tokens 256
```

## Project Structure

- `agent/composite_planner.py`：Rule/Replay/LLM Composite Planner 的公共入口和输出门禁。
- `agent/application/composite_planning.py`：能力目录、事实交接、TaskPlan/binding 前的应用协调。
- `agent/runtime_core/planner_envelope.py`：阶段化、版本化、预算受控的模型输入投影。
- `agent/runtime_core/composite_taskplan.py`、`execution_binding.py`：合法计划和执行身份门禁，不在本阶段复制。
- `evaluation/live_provider_probe.py`、`scripts/live_provider_probe.py`：脱敏、单次、有界真实模型验收。
- `tests/test_m303_open_composite_execution.py`：只覆盖本阶段新增的模型输出到 canonical plan 的独立失败模式。
- `docs/`、`tasks/`：Spec、Plan、问题日志、恢复快照和阶段进度，使用中文记录。

## Code Style

模型输出适配必须是小接口、深实现：调用方只提供结构化候选和原始 JSON，适配器返回 canonical outcome；所有不可信字段先通过 allowlist、长度和 identity 校验。

```python
outcome = planner.plan(request_context)
if outcome.status == "PLANNED":
    binding = materialize_and_validate(outcome.plan)
elif outcome.status == "NEEDS_CLARIFICATION":
    return project_clarification(outcome)
else:
    return project_failure(outcome)
```

- 不在调用方按领域名称判断成功；以 capability identity、workflow、result profile 和 binding 结果判断。
- 不把 provider 原始响应透传到 Result、Evidence 或前端。
- 保持现有状态名、schema version、fingerprint 和错误分类；新增字段必须有版本化投影。
- 中文用户文本与内部 ID 分离，前端只消费结构化 View/Evidence。

## Testing Strategy

1. **Planner contract**：覆盖合法双组件 DAG、单组件、未知能力、空组件、缺事实、非法依赖和额外字段。
2. **Boundary contract**：确认 Rule、Replay、LLM 经过相同 canonical plan、TaskPlan、ToolRegistry 和 binding 门禁；不新增 Runtime 分支。
3. **Cross-entry acceptance**：沿用生产脚本验证 sync/async/artifact/restart、View、Evidence 和 identity 一致。
4. **Static/deployment gate**：阶段收口只集中运行 Docker 精简回归、compileall、architecture strict、Service smoke、Node projection、readiness。
5. **Live acceptance**：显式调用一次真实模型；receipt 只记录 provider/model 的安全身份、状态、错误分类、耗时、请求/重试次数和是否创建 run。

默认 CI 不运行 live provider、浏览器重型矩阵或全量历史评测。

## Boundaries

- **Always**：通过 ToolRegistry、schema、catalog、workflow、TaskPlan 和 execution binding；保持结构化 evidence；在 Docker 中验证 Python/GIS；中文更新进度日志。
- **Ask first**：更换 provider 协议、引入新的运行时依赖、改变公共 schema version、修改 CI 触发策略或改变默认部署模式。
- **Never**：提交密钥；保存 prompt/模型原文；让模型越过 allowlist 直接调用工具；删除失败用例来制造绿色；为单一地区或问句加入分支。

## Success Criteria

1. 一个包含空间与指标目标的开放请求，在模型有合法选择时可生成至少两个已注册组件的 canonical DAG，并通过现有 TaskPlan、workflow、ToolRegistry 和 execution binding。
2. Rule、Replay、LLM 的核心 plan/result/evidence identity 契约一致；新增适配逻辑不修改 Runtime 主循环。
3. 未知能力、空计划、非法依赖、缺少组件事实和不可用数据分别返回结构化拒绝/澄清/不可用状态，均不创建 execution run。
4. 合法计划的同步、异步、artifact、SQLite/restart 和 Console View 使用同一 Result/Evidence 来源。
5. 真实 Docker GIS/Economic 数据至少有一次显式跨域验收；若 provider 超时或返回语义澄清，receipt 明确记录失败平面和 `execution_run_created=false`，不将其计为成功。
6. 新增或替换一个 Domain Pack 的能力声明时，不需要修改公共 Runtime 和前端主流程。
7. 本阶段精简契约、架构门禁、compileall、HTTP、Node 和 readiness 均可重复通过。

## Open Questions

- 中转 provider 是否能在当前延迟预算内稳定返回合法多组件计划，属于 live 验收变量；代码必须先保证失败可解释和可恢复。
- 若真实数据的跨域时间/空间范围不一致，系统应按已有 readiness/事实交接契约澄清或降级，不在本阶段隐式对齐数据。
