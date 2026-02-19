# Repository Guidelines

## Project Structure & Module Organization
- Root contains high-level docs: `SYSTEM_DESIGN.md`, `README.md`, and this guide.
- All application code is in `backend/`.
- Backend source lives in `backend/src/` with feature-first modules:
  - `api/` FastAPI routes and API models
  - `game/` orchestration, tournament logic, player factory
  - `players/` LLM/engine adapters
  - `analysis/` Stockfish-based analysis
  - `db/` SQLModel models and session helpers
  - `config.py` environment-backed settings
- Tests are in `backend/tests/` and mirror runtime modules.
- Utility scripts are in `backend/scripts/`.

## Build, Test, and Development Commands
Run commands from `backend/` unless noted.
- `uv sync` installs runtime + dev dependencies from `pyproject.toml`/`uv.lock`.
- `uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000` starts the API locally.
- `uv run pytest -q` runs the full test suite.
- `uv run ruff check .` runs lint checks.
- `uv run python scripts/run_engine_match.py` runs a local engine-vs-engine match script.

## Coding Style & Naming Conventions
- Python 3.11+ (`backend/pyproject.toml` requires `>=3.11`; `.python-version` is `3.11`).
- Follow PEP 8 with 4-space indentation and explicit type hints.
- Naming: `snake_case` for modules/functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep API schemas in `api/models.py`; avoid defining ad-hoc response dicts in route handlers.

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` for async coverage.
- Test files use `test_*.py`; test names should describe behavior (`test_start_tournament_rejects_when_running`).
- Add or update tests for every behavioral change in API, orchestration, or DB persistence.

## Commit & Pull Request Guidelines
- Current history is minimal (`init`, `Initial commit`); prefer clear imperative commit subjects (example: `add tournament standings endpoint`).
- Keep commits scoped and logically grouped.
- PRs should include:
  - what changed and why
  - impacted modules/endpoints
  - test evidence (command + result, e.g., `uv run pytest -q`)
  - sample request/response for API changes when relevant

## Security & Configuration Tips
- Copy `backend/.env.example` to `.env` and set API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`).
- Do not commit secrets or local runtime artifacts generated during development.
