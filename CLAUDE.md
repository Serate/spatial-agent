# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Spatial Agent is a Python Agent Runtime demo for natural-language spatial analysis. The generic runtime turns a request into a validated plan, dispatches only registered/schema-checked tools, executes GIS or in-memory adapters, and returns a bounded answer plus trace, evidence, provenance, and optional GeoJSON/artifact references. GIS is the first business domain, not the ownership boundary of the runtime.

## Common commands

Run commands from the repository root. PowerShell is the documented host shell.

### Offline development

Use explicit rule planning and the memory backend so a command does not call a real model or require local GIS data:

```powershell
python run_demo.py --planner rule --backend memory "查询洪山区行政区边界"
python run_demo.py --planner rule --backend memory --domain text "请摘要这段文本"
python scripts\build_console.py --check
python scripts\build_console.py
```

The Console has no npm build. `web/src` is the source tree and `scripts/build_console.py` copies supported HTML/CSS/JS assets to `web/dist`.

Start the development HTTP service or Console with:

```powershell
python serve_api.py --host 127.0.0.1 --port 8088
scripts\start_console.ps1 -Mode memory -Port 8088
```

The production API entry point is `production_api:app` (FastAPI); the standard-library `serve_api.py` entry point shares the semantic dispatcher and transport helpers. For a local direct launch, use `uvicorn production_api:app --host 127.0.0.1 --port 8088` after installing `requirements-prod.txt`.

### Tests and validation

The bounded profiles are the normal development interface:

```powershell
python scripts\test_profile.py --profile quick
python scripts\test_profile.py --profile smoke
python scripts\test_profile.py --profile ci
python scripts\test_profile.py --profile stage
```

`quick` is the smallest contract gate; `smoke` exercises the service; `ci` combines quick and smoke; `stage` runs representative offline acceptance cases. Use `full-stage` only for shared Runtime/HTTP/SQLite/deployment/model-evaluation changes. GIS, live model/network, and Docker checks are explicit:

```powershell
python scripts\test_profile.py --profile full-stage
python scripts\test_profile.py --profile gis-core
python scripts\test_profile.py --profile live-short --dataset-config D:\tmp\wuhan-gis\datasets.wuhan.analysis-ready.bound.json --live-output D:\tmp\wuhan-gis\live-short.json
python scripts\test_profile.py --profile docker --docker-base-url http://127.0.0.1:8088
```

Run one module, class, or method directly with `unittest`:

```powershell
python -m unittest tests.test_m334_evidence_quality -v
python -m unittest tests.test_m334_evidence_quality.M334EvidenceIdentityTests.test_same_content_deduplicates_across_urls_without_leaking_secrets -v
```

Before using a historical test name, verify the actual module with `rg --files tests`. Python syntax/import validation is commonly run as:

```powershell
python -m compileall -q agent domains evaluation scripts tests
```

There is no repository-wide lint configuration or dedicated lint script. When Ruff is installed, the documented focused static check is:

```powershell
python -m ruff check agent domains evaluation scripts tests --select F401,F821,F841
```

Treat an unavailable linter as an environment gap, not as a passing check. `git diff --check` is the first whitespace check.

**Important test-discovery caveat:** `tests/__init__.py` defines `load_tests` and intentionally limits top-level `python -m unittest discover -s tests -t . -v` to the compact active modules (`test_dev_gate` and `test_http_contract`), currently only four tests. It is not a full regression command. Use `test_profile.py` or explicit test modules; the large milestone suite is retained as opt-in diagnostic/acceptance coverage.

### Docker and GIS

Rebuild the current tree before container-based evidence:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --force-recreate
python scripts\test_profile.py --profile docker --docker-base-url http://127.0.0.1:8088
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\production_acceptance.ps1 -BaseUrl http://127.0.0.1:8088
```

Keep `--env-file .env.production`: it supplies host-side Compose variable interpolation for the `/data` volume; the service `env_file` alone does not. The image builds a `spatial-agent-gis` environment and generates `web/dist`. Use `conda env create -f environment.yml` and `conda activate spatial-agent-gis` for real local GIS work. Real data is referenced through local config and mounted/read-only; do not assume repository fixtures represent production data.

Live model/network checks are opt-in. The documented model settings are `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_WIRE_API`, and `OPENAI_REASONING_EFFORT`; default tests use rule planning and do not make external model calls.

## Architecture

The canonical request path is:

```text
CLI / serve_api.py / production_api.py / Console
  -> HTTPApplication (shared semantic read/write dispatcher)
  -> AgentService / DomainRuntimeHost
  -> Domain Pack (GIS, Text, Indicators, Economic, ...)
  -> AgentRuntime
  -> request facts/discovery/selection
  -> Rule or LLM planner / bounded ReAct
  -> TaskPlan schema + policy/execution gates
  -> ToolRegistry
  -> domain adapter/backend execution
  -> answer/result/evidence projection
  -> SQLite state, async/recovery, artifacts and Console views
```

### Canonical boundaries

- **Transport:** `serve_api.py` and `production_api.py` are adapters. `agent/application/http.py` owns shared HTTP semantics; `agent/application/http_transport.py` owns framework-neutral JSON, errors, query parsing, and safe artifact access.
- **Application:** `agent/service.py` is a compatibility/application facade. Canonical Run, Session, Action, Decision, Interaction, Async, catalog, inspection, and recovery use cases live under `agent/application/`.
- **Domain routing:** `agent/domain_registry.py`, `agent/domain_selector.py`, and `agent/domain_runtime_host.py` keep registered Domain Packs isolated. Domain-owned request understanding, planners, composers, views, workflow templates, and adapters live under `domains/*`.
- **Runtime:** `agent/runtime_core/` contains planning, validation, execution, budgets/deadlines, progress/events, cancellation/retry/recovery, previews, and projections. `agent/react/` and `agent/runtime_core/react_runtime.py` implement bounded one-action-at-a-time ReAct; it must still use the normal validation, policy, ToolRegistry, execution, and evidence seams.
- **Tools and integration:** `agent/tools.py`/ToolRegistry is the execution boundary. Providers and structured model integration are under `agent/integration/`; controlled web access is under `agent/network/`; dynamic tool proposals are validated and approval-gated through `agent/tooling/` and the isolated sandbox sidecar.
- **Persistence and contracts:** canonical SQLite, memory, artifact, and manifest code is under `agent/persistence/`. `agent/evidence/` owns evidence contracts, source identity/quality, bundles, projections, recovery, and revalidation. `result_contract.py` and the result registry build the bounded public envelope and typed views. Sync, async, artifact, and restart/recovery consumers must share these projections rather than reconstructing fields independently.
- **GIS:** `domains/gis/adapters/` owns GeoJSON/raster/vector backends, data catalog and readiness checks, analysis-ready raster binding, geometry export, and release evidence. The generic runtime must not contain GIS-specific dataset names or thresholds.
- **Console:** source is `web/src`; `web/dist` is generated deployment output and `agent/web_assets.py` selects the generated/source assets. The frontend consumes workspace, view, evidence, and action contracts rather than branching on individual domains.

### Invariants to preserve

1. Planner output is a proposal: it must pass TaskPlan/schema, policy, capability, and data-readiness gates before execution.
2. Tools are invoked only through `ToolRegistry`; HTTP/domain code must not call GIS backends directly.
3. Domain-neutral runtime code must not infer business policy from a Domain Pack name or GIS-specific terms.
4. Result, evidence, artifact, async, SQLite, and restart paths use one versioned public contract and bounded/sanitized projections.
5. Compatibility facades in `agent/` or legacy web entry points delegate one way to canonical implementations; do not add new policy or duplicate logic to them.
6. ReAct/web-fetch/model paths retain bounded budgets, deadlines, allowlists/policy, and safe evidence projections; model responses, prompts, web page bodies, and private configuration are not persisted as public evidence.

## Repository documentation and recovery

For current work, read `docs/agent-work-state.md` and the referenced stage `handoff.md` first, then only the necessary source/tests. `docs/architecture-map.md` describes active seams and invariants; `docs/code-index.json` and `docs/code-index-overrides.json` are the source navigation indexes. `docs/README.md` describes the four-layer documentation system and `scripts/resume_context.ps1` is the bounded recovery entry point.

After adding or renaming source modules, regenerate and validate the code index:

```powershell
python scripts\build_code_index.py --repo-root .
pwsh -NoProfile -File scripts\validate_code_index.ps1
pwsh -NoProfile -File scripts\validate_document_index.ps1
```

Stage plans/specs/handoffs are historical or current task records, not a second runtime implementation. Update the relevant current-state/handoff/index documents when a stage actually changes; do not rewrite completed history merely to reflect a new implementation.
