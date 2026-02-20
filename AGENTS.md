# Repository Guidelines

## Project Structure & Module Organization
- Root contains high-level docs plus deploy/dev setup files: `SYSTEM_DESIGN.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `.env.example`, and `docker-compose.yml`.
- Backend code is in `backend/` (FastAPI + SQLModel + python-chess).
- Frontend code is in `frontend/` (Next.js 16 App Router + React 19 + TypeScript + Tailwind CSS v4).

### Backend
- Runtime source is in `backend/src/`:
  - `api/`: FastAPI routes and API response/request models
  - `game/`: orchestration, tournament manager, player factory, Elo updates, and opening detection (`openings.py`)
  - `players/`: LLM and UCI engine adapters
  - `analysis/`: Stockfish move evaluation and accuracy/CPL classification
  - `db/`: SQLModel entities and DB session/init helpers
  - `config.py`: environment-backed settings (`pydantic-settings`)
- Live API surface includes `/api/live`, `POST /api/tournament/start` (returns run/player payload), and `WS /ws/live`.
- Entrypoints:
  - `backend/main.py` and `backend/src/main.py`
- Utility scripts:
  - `backend/scripts/run_engine_match.py`
  - `backend/scripts/run_llm_match.py`
- Tests:
  - `backend/tests/test_*.py`

### Frontend
- App source is in `frontend/src/`:
  - `app/`: routes (`/`, `/games/[id]`, `/players/[name]`) and global layout/styles
  - `components/`: reusable UI (board, charts, move list, scoreboard, nav)
  - `hooks/`: live tournament state and WebSocket lifecycle
  - `lib/`: typed API client and shared TypeScript interfaces
- Home route supports starting tournaments directly from the UI (calls `POST /api/tournament/start`).
- Config:
  - `frontend/next.config.ts` rewrites `/api/*` and `/health` using `BACKEND_URL` (default `http://localhost:8000`).
  - Browser-side API/WS targets come from `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL`.

## Build, Test, and Development Commands
Run commands from the relevant subdirectory.

### Full stack (`/`)
- `cp .env.example .env` seeds Docker env for backend container keys/settings.
- `docker compose up --build` runs backend (`:8000`) and frontend (`:3000`) together.

### Backend (`backend/`)
- `uv sync` installs dependencies from `pyproject.toml`.
- `uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000` starts the API.
- `curl -X POST http://localhost:8000/api/tournament/start -H 'Content-Type: application/json' -d '{"rounds":1}'` starts a tournament from API.
- `uv run pytest -q` runs backend tests.
- `uv run ruff check .` runs lint checks.
- `uv run python scripts/run_engine_match.py` runs local engine-vs-engine.
- `uv run python scripts/run_llm_match.py` runs local LLM-vs-LLM via OpenRouter (requires `OPENROUTER_API_KEY`; supports `--max-tokens` and `--reasoning-effort`).

### Frontend (`frontend/`)
- `npm install` installs dependencies.
- `npm run dev` starts Next.js dev server (`http://localhost:3000`).
- `npm run build` runs a production build (use as the main frontend validation step).
- `npm run start` serves the production build.

## Coding Style & Naming Conventions

### Python (backend)
- Python `>=3.11`.
- Follow PEP 8, 4-space indentation, and explicit type hints.
- Naming:
  - `snake_case` for modules/functions/variables
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants
- Keep API schemas centralized in `backend/src/api/models.py`.
- Prefer pure, testable orchestration logic in `game/` and persistence logic in `db/`/`tournament.py`.

### TypeScript/React (frontend)
- Keep strict typing; reuse shared interfaces in `frontend/src/lib/types.ts`.
- Keep backend calls in `frontend/src/lib/api.ts` instead of ad-hoc `fetch` calls in components.
- Prefer composable client components and hooks; keep WebSocket/state logic inside hooks.
- Use `PascalCase` for components, `camelCase` for functions/variables.

## Testing Guidelines
- Backend framework is `pytest` with `pytest-asyncio` for async flows.
- Add/update backend tests for behavior changes in API, orchestration, DB persistence, or Elo/stat calculations.
- Use temporary sqlite DBs in tests (see existing API/tournament tests) instead of relying on `backend/arena.db`.
- Frontend currently has no automated test suite in this repo; for frontend changes, at minimum run `npm run build` and manually verify affected routes/components.

## Commit & Pull Request Guidelines
- History is still short (`Initial commit`, `init`, `Phase 3`); use clear imperative commit subjects (example: `add live tournament reconnect handling`).
- Keep commits scoped to one logical change.
- PRs should include:
  - what changed and why
  - impacted backend endpoints/modules and/or frontend routes/components
  - verification evidence (commands + results), e.g. `uv run pytest -q`, `npm run build`
  - API request/response examples for contract changes

## Security & Configuration Tips
- Docker env setup (repo root):
  - `cp .env.example .env`
- Backend env setup:
  - `cp backend/.env.example backend/.env`
  - configure `OPENROUTER_API_KEY` and `STOCKFISH_PATH`
  - optional OpenRouter metadata: `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`; optional API target override: `OPENROUTER_BASE_URL`
  - deprecated fallback aliases are still read during migration: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` (prefer `OPENROUTER_API_KEY`)
  - tune runtime via `DATABASE_URL`, `ANALYSIS_DEPTH`, `STOCKFISH_THREADS`, `STOCKFISH_HASH_MB`, `MOVE_DELAY_SECONDS`, `MAX_MOVES_PER_SIDE`, `LLM_MAX_RETRIES`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_REASONING_EFFORT`
  - optional: set `PLAYERS` as a JSON array to override the default tournament roster in `backend/src/config.py` (current defaults: GPT-5.2, Claude Opus, Gemini 3 Flash, Stockfish-800)
  - `PLAYERS` supports both LLM and engine entries; engine entries can include `engine_path`, `time_limit`, `skill_level`, and `elo_limit`
  - LLM entries in `PLAYERS` should use `provider: "openrouter"` and OpenRouter model IDs (example: `openai/gpt-5.2`), and can include `reasoning_effort`
- Frontend optional env vars:
  - `BACKEND_URL` (used by Next.js rewrites in `next.config.ts`)
  - `NEXT_PUBLIC_API_URL` (REST base URL)
  - `NEXT_PUBLIC_WS_URL` (live WebSocket URL)
- Never commit secrets or local env files.
- Avoid committing runtime artifacts/caches (`__pycache__`, `.next`, local DB churn) unless explicitly intended.
