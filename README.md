# ChessBench — LLM Chess Arena

A platform where LLMs (Claude, GPT-4o, Gemini) play chess against each other and against Stockfish. Games are analyzed move-by-move in real time, with Elo ratings, accuracy metrics, and live spectating via WebSocket.

## Features

- **Live spectating** — watch games unfold in real time with animated board, eval bar, and move-by-move analysis
- **Deep analytics** — per-move Stockfish evaluation, centipawn loss, accuracy charts, and move classification (best/excellent/good/inaccuracy/mistake/blunder)
- **Elo ratings** — K=32 system tracking relative LLM strength across round-robin tournaments
- **ECO opening detection** — automatic opening identification from a ~150-entry ECO table
- **Player profiles** — accuracy distribution histograms, cost tracking, blunder rates
- **Game archive** — full move-by-move replay with keyboard navigation, PGN download, eval/accuracy charts

## Quick Start (Docker)

```bash
cp .env.example .env
# Add your API keys to .env (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Start a tournament: `curl -X POST http://localhost:8000/api/tournament/start -H 'Content-Type: application/json' -d '{"rounds":1}'`

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Stockfish](https://stockfishchess.org/download/) installed and accessible

### Backend

```bash
cd backend
cp .env.example .env    # Add API keys and set STOCKFISH_PATH
uv sync
uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev              # Starts on http://localhost:3000
```

The frontend dev server proxies `/api/*` requests to `localhost:8000` automatically.

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
│              FRONTEND (Next.js 15 + TypeScript)         │
│                                                         │
│  Live Board ─── Scoreboard ─── Game Archive ─── Player  │
│  (react-        (Elo, W/L/D    (replay, PGN    Profile  │
│   chessboard)    accuracy)      eval charts)   (stats)  │
│                       │                                  │
│                  WebSocket + REST (via proxy)            │
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
│  ├── LLMPlayer (OpenAI / Anthropic / Google)            │
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
| POST | `/api/tournament/start` | Start a tournament |
| WS | `/ws/live` | Live game WebSocket |

## License

MIT
