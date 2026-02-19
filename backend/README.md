# ChessBench Backend

## Setup

```bash
uv sync
cp .env.example .env
```

## Run FastAPI

```bash
uv run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

## Start Tournament (Phase 3)

```bash
curl -X POST http://localhost:8000/api/tournament/start \
  -H "content-type: application/json" \
  -d '{"rounds":1}'
```

## Phase 3 APIs

- `GET /api/standings`
- `GET /api/games?limit=20&offset=0`
- `GET /api/games/{game_id}`
- `GET /api/games/{game_id}/analysis`
- `GET /api/players/{player_name}/stats`
- `GET /api/live`
- `WS /ws/live`

## Run Tests

```bash
uv run pytest -q
```
