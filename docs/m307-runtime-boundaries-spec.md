# Spec：M307 Agent Runtime 生命周期与传输边界收敛

## Objective

确认通用 Agent Runtime 的核心编排、HTTP 语义 seam 和兼容模块守卫已经达到目标，并只补齐文档与契约证据，不为已经存在的深模块增加新的浅包装。

用户仍然只需要提交自然语言请求。系统对外行为必须保持兼容：请求理解、澄清、规划、校验/有限修复、工具执行、答案、证据、artifact、异步和重启恢复使用现有契约；内部阶段证据可以说明当前阶段和失败原因，但不输出模型原文、prompt、密钥或内部思维链。

## Assumptions

1. 现有 Runtime、HTTPApplication、FastAPI 和 stdlib 入口是生产基线，公共请求/结果 schema 不改版本。
2. `run_lifecycle.py` 的阶段函数只负责编排边界，领域算法仍由 Domain Pack 和 ToolRegistry 提供。
3. 传输层共享抽象以保持现有 URL、HTTP 方法、状态码和 JSON envelope；若发现历史入口存在有意差异，保留显式 adapter，而不是隐式改变语义。
4. 被误标为 compat 的真实公共模块先移出豁免清单并接受守卫；只有确认无生产导入后才删除 shim，删除动作需要单独、可恢复地验证。

## Tech Stack

- Python 3.11、现有 Agent Runtime、FastAPI、stdlib `http.server`。
- Docker Compose 生产镜像作为 Python、GIS、compileall 和架构门禁环境。
- `unittest` 精简契约测试、Node projection smoke、现有 HTTP/生产 acceptance。

## Commands

所有 Python、GIS 和架构检查在 Docker 中执行，且不读取或打印 `.env.production` 内容：

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build --force-recreate spatial-agent
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m unittest tests.test_m307_runtime_boundaries -v
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python -m compileall -q agent domains production_api.py serve_api.py
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/architecture_check.py --strict
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent node scripts/console_result_projection_smoke.js
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm spatial-agent python scripts/smoke_check.py
Invoke-WebRequest -Uri 'http://127.0.0.1:8088/health/ready' -UseBasicParsing
```

## Project Structure

- `agent/runtime_core/run_lifecycle.py`：阶段编排与生命周期转换。
- `agent/application/`、`agent/runtime_core/`：公共应用和 Runtime seam。
- `agent/application/http.py`：共享 HTTP 语义与传输边界。
- `production_api.py`、`serve_api.py`：部署入口适配，不复制业务分派。
- `scripts/architecture_check.py`：模块边界和兼容清单守卫。
- `tests/test_m262_architecture_convergence.py`、`tests/test_m256_http_application.py`：本阶段复用的最小契约。
- `docs/`、`tasks/`：Spec、Plan、阶段记录和恢复快照。

## Code Style

阶段函数使用稳定输入/输出和有界 receipt，现有实现已经满足这一 seam：

```python
def run(request: str, **options: Any) -> AgentRunResult:
    resolved = self._resolve(request, options)
    clarified = self._clarify(resolved)
    planned = self._plan(clarified)
    validated = self._validate_or_repair(planned)
    executed = self._execute(validated)
    answered = self._answer(executed)
    return self._attach_evidence(answered)
```

- 阶段名使用小写稳定标识；状态转换继续由现有生命周期契约统一产生。
- 阶段函数不直接访问 HTTP request、环境密钥或领域专用实现。
- 共享传输函数返回结构化 envelope；入口只负责框架 request/response 转换。
- FastAPI/stdlib 的路由声明差异属于框架适配，不在公共 Runtime 中复制业务语义。
- 兼容模块分类必须由实际 import/守卫结果证明，不以文件名猜测。

## Testing Strategy

- 契约层：验证阶段顺序、阶段异常到统一 failure/evidence、成功结果不变、一次有限 repair 不重复执行。
- 传输层：验证 FastAPI 与 stdlib 对代表性语义命令产生一致的 status/envelope；不重复完整业务测试。
- 架构层：验证真实公共模块不再走 compat 豁免，保留 shim 的导入兼容和禁止跨边界依赖。
- 阶段收口：Docker 中集中运行本阶段契约、相邻代表性回归、compileall、architecture strict、Node projection、service smoke、readiness 和必要的 HTTP/artifact/restart acceptance。
- 真实模型只在确实改变 provider-facing 行为且离线门禁通过时显式调用一次；本阶段不因结构性重构重复 M306 live。

## Boundaries

- Always：先保持公共 schema/状态契约，再拆内部阶段；所有工具仍经 ToolRegistry；所有 Python/GIS 检查在 Docker；每个子任务更新任务账本。
- Ask first：删除仍可能被外部使用的兼容 shim、修改公共 HTTP URL/状态码、改变 CI 触发策略或新增运行时依赖。
- Never：为通过测试删除失败断言；绕过 canonical TaskPlan、DAG、execution binding 或 ToolRegistry；提交密钥、模型原文、prompt、私有路径或完整数据；以传输层分支复制领域逻辑。

## Success Criteria

1. `run_lifecycle.py` 的公开 `run()` 不再承载完整阶段实现；阶段顺序可通过最小契约验证，现有同步/异步/恢复结果契约不漂移。
2. 阶段失败、澄清、有限 repair 和成功均保留统一、可读、有界的生命周期/evidence，且不会重复执行已完成工具。
3. FastAPI 与 stdlib 入口的代表性 HTTP 语义共享 `HTTPApplication`/`http_transport` 分派与编码边界；入口文件只保留框架适配代码。
4. 架构检查不再以 `COMPAT_MODULES` 豁免真实公共引擎模块；保留的 shim 有明确清单和兼容测试。
5. Docker 中本阶段精简契约、相邻回归、compileall、architecture strict、Node projection、service smoke 和 readiness 全部通过。
6. 阶段文档、中文问题日志、任务账本、恢复快照和版本记录完整，未保存敏感信息。

## Open Questions

- 当前无阻塞问题。若传输入口存在无法等价抽取的历史差异，在实现阶段以显式 adapter 记录，不擅自改变外部行为。
