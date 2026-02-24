# ChessBench: LLM Chess Arena

A platform where LLMs and engines play chess against each other with live analysis. The default roster currently includes OpenAI GPT 5.2, Claude Sonnet 4.6, and Gemini 3 Flash Preview. Games are analyzed move-by-move in real time, with Elo ratings, accuracy metrics, and live spectating via WebSocket.

## Features

- **Live spectating** — watch games unfold in real time with animated board, eval bar, and move-by-move analysis
- **One-click tournament start** — launch a tournament directly from the home page (or via API)
- **Deep analytics** — per-move Stockfish evaluation, centipawn loss, accuracy charts, and move classification (best/excellent/good/inaccuracy/mistake/blunder)
- **Elo ratings** — K=32 system tracking relative LLM strength across round-robin tournaments
- **ECO opening detection** — automatic opening identification from a ~150-entry ECO table
- **Player profiles** — accuracy distribution histograms, cost tracking, blunder rates
- **Game archive** — full move-by-move replay with keyboard navigation, PGN download, eval/accuracy charts

## Quick Start (Docker)

```bash
cp .env.example .env
# Add your OpenRouter API key to .env (OPENROUTER_API_KEY)
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Start a tournament from the UI button on `/`, or via API:
  `curl -X POST http://localhost:8000/api/tournament/start -H 'Content-Type: application/json' -d '{"rounds":1}'`

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Stockfish](https://stockfishchess.org/download/) installed and accessible

### Backend

```bash
cd backend
cp .env.example .env    # Add OPENROUTER_API_KEY (optionally set STOCKFISH_PATH override)
uv sync
uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

If `STOCKFISH_PATH` is unset, ChessBench auto-detects `stockfish` from `PATH`.

Deprecated key aliases (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) are still accepted as fallback during migration, but `OPENROUTER_API_KEY` is the canonical setting.
`LLM_MAX_TOKENS` defaults to `128` to keep move generation token usage low.
`LLM_REASONING_EFFORT` defaults to `none` and is applied uniformly to all LLM players for controlled comparisons.
When this global value is set, per-player `reasoning_effort` values are ignored to keep tournaments on equal footing.
Set `OPENROUTER_HTTP_REFERER` to your app URL (for example `http://localhost:3000`) and optionally set `OPENROUTER_X_TITLE=ChessBench` for OpenRouter attribution headers.

Optional roster override via env:

```bash
export PLAYERS='[
  {"name":"Stockfish-1200","provider":"engine","model":"stockfish","elo_limit":1200},
  {"name":"Stockfish-800","provider":"engine","model":"stockfish","elo_limit":800}
]'
```

### Frontend

```bash
cd frontend
npm install
npm run dev              # Starts on http://localhost:3000
```

Browser API/WS targets are controlled by:
- `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`)
- `NEXT_PUBLIC_WS_URL` (default `ws://localhost:8000/ws/live`)

### Local LLM-vs-LLM Script

`backend/scripts/run_llm_match.py` now uses OpenRouter only.

```bash
cd backend
uv run python scripts/run_llm_match.py \
  --white-model openai/gpt-5.2 \
  --black-model anthropic/claude-sonnet-4.6 \
  --max-tokens 128 \
  --reasoning-effort none
```

## Tournament Start Response

`POST /api/tournament/start` returns `202 Accepted` and includes the active player config list:

```json
{
  "status": "accepted",
  "run_id": "abc123def4",
  "rounds": 1,
  "players": [
    { "name": "OpenAI GPT 5.2", "provider": "openrouter", "model": "openai/gpt-5.2" },
    { "name": "Claude Sonnet 4.6", "provider": "openrouter", "model": "anthropic/claude-sonnet-4.6" },
    { "name": "Gemini 3 Flash Preview", "provider": "openrouter", "model": "google/gemini-3-flash-preview" }
  ]
}
```

## Running Tests

```bash
cd backend
uv run pytest -q         # Run full test suite
uv run ruff check .      # Lint
```

```bash
cd frontend
npm run build            # Type-check (no ESLint configured)
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│        FRONTEND (Next.js 16 + React 19 + TypeScript)     │
│                                                         │
│  Live Board ─── Scoreboard ─── Game Archive ─── Player  │
│  (react-        (Elo, W/L/D    (replay, PGN    Profile  │
│   chessboard)    accuracy)      eval charts)   (stats)  │
│                       │                                  │
│            WebSocket + REST (configurable URLs)          │
└───────────────────────┼─────────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────────┐
│              BACKEND (FastAPI + SQLite)                  │
│                                                         │
│  REST API ──── WebSocket ──── Tournament Manager         │
│  (games,       (live move     (round-robin,              │
│   standings,    broadcast)     Elo updates)              │
│   players)          │                                    │
│                     │                                    │
│  Game Orchestrator ──── Stockfish Analyzer               │
│  (turn loop,             (per-move eval,                 │
│   move validation)        CPL, classification)           │
│           │                                              │
│  Player Adapters                                         │
│  ├── LLMPlayer (OpenRouter)                             │
│  └── UCIEnginePlayer (Stockfish)                        │
└─────────────────────────────────────────────────────────┘
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/standings` | Current Elo standings |
| GET | `/api/games` | List games (paginated) |
| GET | `/api/games/{id}` | Game detail |
| GET | `/api/games/{id}/analysis` | Move-by-move analysis |
| GET | `/api/players/{name}/stats` | Player statistics |
| GET | `/api/players/{name}/accuracy-distribution` | Move classification counts |
| GET | `/api/live` | Current live state |
| POST | `/api/tournament/start` | Start a tournament (202 accepted with run/player payload) |
| WS | `/ws/live` | Live game WebSocket |

## License

MIT
