# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChessBench is an LLM Chess Arena — a platform where LLMs (Claude, GPT-4o, Gemini) play chess against each other and against Stockfish. Games are analyzed move-by-move by Stockfish in real-time, with Elo ratings, accuracy metrics, and live spectating via WebSocket.

**Status:** All phases (1-5) complete. See `SYSTEM_DESIGN.md` for the full design spec.

## Commands

### Backend (run from `backend/`)

```bash
uv sync                    # Install dependencies
uv run pytest -q           # Run full test suite
uv run pytest tests/test_elo.py -q          # Run a single test file
uv run pytest tests/test_elo.py::test_name  # Run a single test
uv run ruff check .        # Lint
uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000  # Dev server
```

### Frontend (run from `frontend/`)

```bash
npm install                # Install dependencies
npm run dev                # Dev server on port 3000
npm run build              # Production build (also serves as type-check)
```

### Running the full stack (dev)

1. Start backend: `cd backend && uv run uvicorn src.api.server:app --reload --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:3000`
4. Start a tournament: `curl -X POST http://localhost:8000/api/tournament/start -H 'Content-Type: application/json' -d '{"rounds":1}'`

### Running the full stack (Docker)

```bash
cp .env.example .env     # Add API keys to .env
docker compose up --build
```

Frontend at `http://localhost:3000`, backend API at `http://localhost:8000`.

## Architecture

### Backend

All backend code is in `backend/src/` using feature-first modules:

- **`players/`** — `PlayerAdapter` ABC (`base.py`) with implementations: `LLMPlayer` (OpenAI/Anthropic/Google) and `UCIEnginePlayer` (Stockfish). Every adapter returns a `MoveResult` dataclass with the move, tokens, cost, think time, and illegal attempt count.
- **`analysis/`** — `StockfishAnalyzer` evaluates each move immediately after it's played. Uses Lichess-style accuracy formula and classifies moves (best/excellent/good/inaccuracy/mistake/blunder) based on centipawn loss.
- **`game/`** — `GameOrchestrator` runs the core game loop (alternating moves with per-move analysis), emitting `LiveMoveEvent`s for real-time updates. `TournamentManager` handles round-robin scheduling and Elo updates (K=32, start 1200). `PlayerFactory` builds adapters from config. `openings.py` detects ECO openings from PGN via a ~150-entry lookup table (longest match wins).
- **`api/`** — FastAPI REST endpoints + WebSocket at `/ws/live`. Response schemas live in `api/models.py`.
- **`db/`** — SQLModel tables (`Player`, `Game`, `MoveAnalysis`, `Tournament`) with SQLite default. Session factory in `session.py`.
- **`config.py`** — Pydantic `BaseSettings` loading from `.env`. Contains player roster, Stockfish path, LLM retry/temperature settings, DB URL.

### Frontend

Next.js 15 (App Router) + TypeScript + Tailwind CSS 4. All source in `frontend/src/`.

- **`app/page.tsx`** — Live spectating page. Uses `useGameState()` hook for WebSocket-driven real-time updates (board, eval bar, move list, scoreboard).
- **`app/games/[id]/page.tsx`** — Game archive with move-by-move navigation (arrow keys + buttons), eval/accuracy charts, move analysis table, PGN download.
- **`app/players/[name]/page.tsx`** — Player profile with stat cards (Elo, accuracy, CPL, blunder rate, cost) and accuracy distribution histogram.
- **`lib/types.ts`** — TypeScript types mirroring backend Pydantic models in `api/models.py`. Includes `WSEvent` discriminated union for all WebSocket event types.
- **`lib/api.ts`** — Thin REST client wrapping each backend endpoint. Base URL from `NEXT_PUBLIC_API_URL` env var.
- **`hooks/useWebSocket.ts`** — WebSocket with auto-reconnect (exponential backoff 1s→30s max).
- **`hooks/useGameState.ts`** — `useReducer`-based state machine handling all WS events + late-join hydration via `GET /api/live`.
- **`components/`** — `LiveBoard` (react-chessboard), `EvalBar`, `EvalChart`/`AccuracyChart`/`AccuracyDistributionChart` (recharts), `MoveList`, `Scoreboard`, `PlayerCard`, `Navigation`.

**Dev proxy:** `next.config.ts` rewrites `/api/*` and `/health` to backend (configurable via `BACKEND_URL` env var, defaults to `http://localhost:8000`). Next.js is configured with `output: "standalone"` for Docker builds.

**Environment:** `frontend/.env.local` must set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` (defaults to `http://localhost:8000` and `ws://localhost:8000/ws/live`).

### Docker

- `docker-compose.yml` at project root orchestrates `backend` and `frontend` services
- Backend Dockerfile: Python 3.11-slim + Stockfish binary + uv
- Frontend Dockerfile: multi-stage Node 20 build (deps → builder → standalone runner)
- Persistent SQLite volume at `/app/data/arena.db`
- Root `.env.example` has Docker-appropriate defaults (`STOCKFISH_PATH=/usr/local/bin/stockfish`)

## Key Design Decisions

- LLMs receive **FEN + legal moves list** (not PGN completion) for structured prompting
- Illegal move responses trigger retries with SAN/UCI fallback parsing (`llm_max_retries=5`)
- Analysis is **per-move in real-time** (not post-game batch), enabling live eval bar updates
- Primary metric is **centipawn loss (CPL)**; accuracy uses the Lichess formula: `103.1668 * exp(-0.04354 * min(cpl, 1000)) - 3.1668`
- **ECO opening detection** matches game PGN against a ~150-entry table sorted longest-first; `Game` DB model stores `opening_eco`/`opening_name` (nullable)

## Coding Conventions

### Backend
- Python 3.11+, PEP 8, 4-space indent, explicit type hints
- `snake_case` for modules/functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- API schemas in `api/models.py` — no ad-hoc response dicts in handlers
- Tests use `pytest` + `pytest-asyncio`; test names describe behavior (e.g., `test_start_tournament_rejects_when_running`)
- Environment: copy `backend/.env.example` to `.env` and set API keys before running (for Docker, use root `.env.example` instead)

### Frontend
- All pages/components are `"use client"` (no RSC)
- `react-chessboard` v5 uses an `options` prop (not flat props): `<Chessboard options={{ position, boardOrientation, ... }} />`
- `motion` library is imported from `"motion/react"` (not `"framer-motion"`)
- Classification colors use CSS custom properties (`var(--clr-best)` through `var(--clr-blunder)`) defined in `globals.css`
- Fonts: Space Grotesk (display), DM Sans (body), JetBrains Mono (code) — loaded via `next/font/google`
- No ESLint configured; `npm run build` serves as the type-check gate
- Frontend TypeScript types must stay in sync with backend `api/models.py` schemas
