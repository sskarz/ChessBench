<div align="center">
  <img src="frontend/public/logo.png" alt="ChessBench" width="120" />
  <h1>ChessBench</h1>
  <p><strong>LLM Chess Benchmark Platform</strong></p>
  <p>
    Pit frontier LLMs against Stockfish. Analyze every move. Estimate Elo from real gameplay.
  </p>

  <p>
    <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/node-20+-339933?logo=node.js&logoColor=white" alt="Node.js" />
    <img src="https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
    <img src="https://img.shields.io/github/license/sskarz/ChessBench?color=blue" alt="License" />
  </p>
</div>

---

GPT-5.2, Claude Opus 4.6, Gemini 3 Flash, and more — all playing chess against Stockfish through [OpenRouter](https://openrouter.ai). Every move is analyzed in real time by Stockfish, producing centipawn loss, accuracy scores, move classifications, and estimated Elo ratings. Watch it all happen live via WebSocket.

## Features

| | Feature | Description |
|---|---|---|
| **Live Spectating** | Real-time board | Animated chessboard, eval bar, and move-by-move analysis streamed over WebSocket |
| **Deep Analysis** | Per-move Stockfish eval | Centipawn loss, accuracy (Lichess formula), move classification: best / excellent / good / inaccuracy / mistake / blunder |
| **Elo Estimation** | CPL-based ratings | Estimated Elo derived from aggregate centipawn loss and win/draw/loss record |
| **Player Profiles** | Stats & histograms | Accuracy distribution, cost tracking, blunder rates, per-player performance |
| **Game Archive** | Full replay | Move-by-move navigation (keyboard + buttons), eval/accuracy charts, PGN download |
| **Opening Detection** | ECO lookup | Automatic opening identification from a ~150-entry ECO table |
| **One-Click Start** | UI or API | Launch a benchmark from the homepage button or a single `POST` request |

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/sskarz/ChessBench.git
cd ChessBench
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
docker compose up --build
```

> **Frontend** `http://localhost:3000` &nbsp;&middot;&nbsp; **API** `http://localhost:8000`

Hit the **Start Benchmark** button on the homepage, or:

```bash
curl -X POST http://localhost:8000/api/benchmark/start \
  -H 'Content-Type: application/json' \
  -d '{"rounds": 1}'
```

### Local Development

<details>
<summary><strong>Prerequisites</strong></summary>

- Python 3.11+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Stockfish](https://stockfishchess.org/download/) installed and on `PATH`

</details>

**Backend**

```bash
cd backend
cp .env.example .env    # Set OPENROUTER_API_KEY
uv sync
uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev             # http://localhost:3000
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│          FRONTEND  (Next.js 16 · React 19 · TypeScript)      │
│                                                              │
│   Live Board ──── Scoreboard ──── Game Archive ──── Player   │
│   (react-         (Elo, W/L/D     (replay, PGN     Profile  │
│    chessboard)     accuracy)       eval charts)    (stats)   │
│                        │                                     │
│             WebSocket + REST  (configurable URLs)            │
└────────────────────────┼─────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────┐
│               BACKEND  (FastAPI · SQLite)                    │
│                                                              │
│   REST API ───── WebSocket ───── Benchmark Manager           │
│   (games,        (live move      (LLM vs Stockfish,          │
│    standings,     broadcast)      Elo estimation)            │
│    players)           │                                      │
│                       │                                      │
│   Game Orchestrator ──── Stockfish Analyzer                  │
│   (turn loop,              (per-move eval,                   │
│    move validation)         CPL, classification)             │
│            │                                                 │
│   Player Adapters                                            │
│   ├── LLMPlayer (OpenRouter — all models)                   │
│   └── UCIEnginePlayer (Stockfish)                           │
└──────────────────────────────────────────────────────────────┘
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/standings` | Current Elo standings |
| `GET` | `/api/games` | List games (paginated) |
| `GET` | `/api/games/{id}` | Game detail |
| `GET` | `/api/games/{id}/analysis` | Move-by-move analysis |
| `GET` | `/api/players/{name}/stats` | Player statistics |
| `GET` | `/api/players/{name}/accuracy-distribution` | Move classification counts |
| `GET` | `/api/live` | Current live game state |
| `POST` | `/api/benchmark/start` | Start a benchmark run |
| `WS` | `/ws/live` | Live game WebSocket |

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | **Required.** OpenRouter API key | — |
| `STOCKFISH_PATH` | Path to Stockfish binary | Auto-detected from `PATH` |
| `LLM_MAX_TOKENS` | Max tokens per move response | `128` |
| `LLM_REASONING_EFFORT` | Reasoning effort for all LLMs | `none` |
| `NEXT_PUBLIC_API_URL` | Frontend API base URL | `http://localhost:8000` |
| `NEXT_PUBLIC_WS_URL` | Frontend WebSocket URL | `ws://localhost:8000/ws/live` |

**Custom player roster** (override via env):

```bash
export PLAYERS='[
  {"name":"Stockfish-1200","provider":"engine","model":"stockfish","elo_limit":1200},
  {"name":"Stockfish-800","provider":"engine","model":"stockfish","elo_limit":800}
]'
```

## Running Tests

```bash
# Backend
cd backend
uv run pytest -q
uv run ruff check .

# Frontend (type-check)
cd frontend
npm run build
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, react-chessboard, Recharts |
| Backend | FastAPI, SQLModel, SQLite, python-chess |
| LLM Gateway | OpenRouter (OpenAI-compatible API) |
| Analysis Engine | Stockfish (UCI) |
| Infrastructure | Docker Compose, uv |

## License

[MIT](LICENSE)
