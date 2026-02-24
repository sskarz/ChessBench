# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChessBench is an LLM Chess Benchmark — a platform where LLMs (Claude, GPT-5.2, Gemini) play chess against Stockfish via **OpenRouter** as a unified API gateway. Games are analyzed move-by-move by Stockfish in real-time, with Elo ratings estimated from CPL, accuracy metrics, and live spectating via WebSocket.

## Commands

### Backend (run from `backend/`)

```bash
uv sync                    # Install dependencies
uv run pytest -q           # Run full test suite
uv run pytest tests/test_benchmark_manager.py -q  # Run a single test file
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
4. Start a benchmark: `curl -X POST http://localhost:8000/api/benchmark/start -H 'Content-Type: application/json' -d '{"rounds":1}'`

Default players: `openai/gpt-5.2`, `anthropic/claude-opus-4-6`, `google/gemini-3-flash-preview` (all via OpenRouter), benchmarked against Stockfish-800.

### Running the full stack (Docker)

```bash
cp .env.example .env     # Add API keys to .env
docker compose up --build
```

Frontend at `http://localhost:3000`, backend API at `http://localhost:8000`.

## Architecture

### Backend

All backend code is in `backend/src/` using feature-first modules:

- **`players/`** — `PlayerAdapter` ABC (`base.py`) with implementations: `LLMPlayer` (all LLMs via OpenRouter's OpenAI-compatible API) and `UCIEnginePlayer` (Stockfish). Every adapter returns a `MoveResult` dataclass with the move, tokens, cost, think time, and illegal attempt count.
- **`analysis/`** — `StockfishAnalyzer` evaluates each move immediately after it's played. Uses Lichess-style accuracy formula and classifies moves (best/excellent/good/inaccuracy/mistake/blunder) based on centipawn loss. `elo_estimator.py` estimates Elo from aggregate CPL and win/draw/loss record.
- **`game/`** — `GameOrchestrator` runs the core game loop (alternating moves with per-move analysis), emitting `LiveMoveEvent`s for real-time updates. `BenchmarkManager` handles benchmark scheduling (LLMs vs Stockfish) and CPL-to-Elo estimation. `PlayerFactory` builds adapters from config (supports `openrouter` and `engine` providers). `openings.py` detects ECO openings from PGN via a ~150-entry lookup table (longest match wins).
- **`api/`** — FastAPI REST endpoints + WebSocket at `/ws/live`. Response schemas live in `api/models.py`.
- **`db/`** — SQLModel tables (`Player`, `Game`, `MoveAnalysis`, `Tournament`) with SQLite default. Session factory in `session.py`.
- **`config.py`** — Pydantic `BaseSettings` loading from `.env`. Contains OpenRouter credentials, player roster, Stockfish path, LLM retry/temperature/max-tokens/reasoning-effort settings, DB URL.

### Frontend

Next.js 16 (App Router) + TypeScript + Tailwind CSS 4. All source in `frontend/src/`.

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

### Scripts

- **`backend/scripts/run_llm_match.py`** — CLI tool for running ad-hoc LLM vs LLM games outside the benchmark system. Uses OpenRouter provider. Run: `uv run python -m scripts.run_llm_match --white-model openai/gpt-4o --black-model anthropic/claude-sonnet-4`

### Branding

- Logo at `frontend/public/logo.png`, referenced as favicon in `layout.tsx` and displayed (with `invert` CSS class) in `Navigation.tsx`

## Key Design Decisions

- **Benchmark-only architecture** — LLMs play against Stockfish (not each other). Elo is estimated from CPL using the Lichess accuracy formula, not from head-to-head results. This eliminates the complexity of round-robin tournament scheduling and Glicko-2 rating updates.
- **OpenRouter as unified LLM gateway** — all LLM calls (OpenAI, Anthropic, Google models) go through OpenRouter's OpenAI-compatible API. This replaces the previous per-provider SDK approach (`openai`, `anthropic`, `google-genai`). Set `OPENROUTER_API_KEY` in `.env`; legacy per-provider keys (`OPENAI_API_KEY`, etc.) are supported as deprecated fallbacks.
- LLMs receive **FEN + legal moves list** (not PGN completion) for structured prompting; system prompt asks for UCI-format responses
- **Robust move extraction** — `LLMPlayer._extract_move_from_response()` tries direct UCI/SAN parsing first, then regex-scans the response for UCI and SAN candidates. This handles verbose/chatty model responses gracefully.
- Illegal move responses trigger retries with SAN/UCI fallback parsing (`llm_max_retries=5`)
- **Reasoning effort control** — configurable via `LLM_REASONING_EFFORT` env var or per-player `reasoning_effort` field. GPT-5.x models default to `"none"` to avoid reasoning overhead. If a response comes back empty due to `finish_reason=length`, a recovery request is sent with higher `max_tokens` and `reasoning_effort="none"`.
- Analysis is **per-move in real-time** (not post-game batch), enabling live eval bar updates
- Primary metric is **centipawn loss (CPL)**; accuracy uses the Lichess formula: `103.1668 * exp(-0.04354 * min(cpl, 1000)) - 3.1668`
- **CPL-to-Elo estimation** — `elo_estimator.py` converts aggregate CPL into an estimated Elo, with separate white/black estimates weighted by qualifying move count. Confidence levels (none/low/high) based on minimum qualifying moves threshold.
- **ECO opening detection** matches game PGN against a ~150-entry table sorted longest-first; `Game` DB model stores `opening_eco`/`opening_name` (nullable)
- **Cost extraction from OpenRouter** — `LLMPlayer` extracts cost from multiple possible response locations (usage.cost, usage.total_cost, etc.) to handle varying OpenRouter response formats

## Coding Conventions

### Backend
- Python 3.11+, PEP 8, 4-space indent, explicit type hints
- `snake_case` for modules/functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- API schemas in `api/models.py` — no ad-hoc response dicts in handlers
- Tests use `pytest` + `pytest-asyncio`; test names describe behavior (e.g., `test_benchmark_manager_rejects_concurrent_run`)
- Environment: copy `backend/.env.example` to `.env` and set `OPENROUTER_API_KEY` before running (for Docker, use root `.env.example` instead). Legacy per-provider keys are deprecated fallbacks.

### Frontend
- All pages/components are `"use client"` (no RSC)
- `react-chessboard` v5 uses an `options` prop (not flat props): `<Chessboard options={{ position, boardOrientation, ... }} />`
- `motion` library is imported from `"motion/react"` (not `"framer-motion"`)
- Classification colors use CSS custom properties (`var(--clr-best)` through `var(--clr-blunder)`) defined in `globals.css`
- Fonts: Space Grotesk (display), DM Sans (body), JetBrains Mono (code) — loaded via `next/font/google`
- No ESLint configured; `npm run build` serves as the type-check gate
- Frontend TypeScript types must stay in sync with backend `api/models.py` schemas
