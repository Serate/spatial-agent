# Repository Guidelines

## Project Structure & Module Organization

- `agent/` contains the runtime, planners, domain packs, tool registry, persistence, and shared HTTP application/adapters.
- `run_demo.py`, `serve_api.py`, and `production_api.py` are the CLI, standard-library service, and FastAPI entry points.
- `tests/` holds the compact unittest and contract suites; `evaluation/` contains acceptance cases and cross-entry harnesses.
- `web/` contains the Console, `config/` contains safe configuration examples, `docs/` contains architecture, API, testing, and milestone guidance, and `scripts/` contains startup and test-profile helpers.
- Keep real datasets, local secrets, generated artifacts, and temporary outputs outside version control (`data/`, `outputs/`, and local `.env` files are environment-specific).

## Build, Test, and Development Commands

Use Python 3.10+. For the deterministic offline loop, run:

```powershell
python run_demo.py "查询洪山区行政区边界"
python scripts\test_profile.py --profile quick
python scripts\test_profile.py --profile ci
```

`quick` checks core contracts; `ci` combines the required quick and smoke checks. Use `python scripts\test_profile.py --profile stage` for representative offline acceptance, and `python -m unittest discover -s tests -t . -v` when auditing the active unittest suite. Start the memory Console with `scripts\start_console.ps1 -Mode memory -Port 8088`. Production checks use `docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d` followed by the readiness and acceptance commands in `README.md`.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, type hints, focused docstrings, `snake_case` functions/modules, `PascalCase` classes, and `UPPER_SNAKE_CASE` constants. Preserve stable API, artifact, event, and evidence contracts. Put shared behavior in `agent/application/` or domain modules rather than duplicating transport logic in entry points. Run `python -m compileall agent tests` and `git diff --check` before submitting.

## Testing Guidelines

Tests use `unittest`; name files `test_*.py` and methods `test_*`. Add or update contract tests with behavior changes. Default tests must use the rule planner and memory backend and must not call external models. Real GIS, live OpenAI, and Docker tests are explicit profiles only (`gis-core`, `live-short`, or `docker`).

## Commit & Pull Request Guidelines

Use a concise, scoped subject such as `docs: ...`, `refactor: ...`, or `M336: ...`. PRs should explain the behavior change, list validation commands and results, note configuration or migration impact, link the relevant issue/stage, and include Console screenshots when UI behavior changes.

## Security & Configuration Tips

Copy example files before editing local configuration. Never commit API keys, `.env.production`, `config/openai.local.json`, private datasets, or generated run artifacts. Treat spatial suitability output as a demonstration, not a regulatory conclusion.
