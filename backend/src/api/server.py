from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_
from sqlmodel import Session, select

from src.api.models import (
    AccuracyDistribution,
    GameAnalysisResponse,
    GameDetail,
    GameListResponse,
    GameSummary,
    HealthResponse,
    LiveStateResponse,
    MoveAnalysisEntry,
    PlayerStats,
    StandingsEntry,
    TournamentStartRequest,
    TournamentStartResponse,
)
from src.config import settings
from src.db.models import Game, MoveAnalysis, Player, Tournament
from src.db.session import engine, get_session, init_db
from src.game.player_factory import build_players_from_settings, describe_player_config
from src.game.tournament import TournamentManager
from src.players.base import PlayerAdapter
from src.players.engine_player import UCIEnginePlayer

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        data = json.dumps(message, default=str)
        stale: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(data)
            except Exception:
                stale.append(ws)

        for ws in stale:
            self.disconnect(ws)


@dataclass
class LiveState:
    status: str = "idle"
    run_id: str | None = None
    active_games: dict[int, dict[str, Any]] = field(default_factory=dict)
    current_game: dict[str, Any] | None = None  # backward compat: most recent game
    last_event: dict[str, Any] | None = None
    last_events: dict[int, dict[str, Any]] = field(default_factory=dict)
    latest_standings: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    error: str | None = None


class AppRuntime:
    def __init__(self) -> None:
        self.manager = ConnectionManager()
        self.live = LiveState(updated_at=datetime.utcnow())
        self.tournament_task: asyncio.Task[Any] | None = None


runtime = AppRuntime()


def _now() -> datetime:
    return datetime.utcnow()


def _is_benchmark_anchor_row(player: Player) -> bool:
    return (
        player.provider == "engine"
        and player.model_id == "stockfish"
        and player.name.startswith("Stockfish-")
    )


def _new_session() -> Session:
    return Session(engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    runtime.live.updated_at = _now()
    yield


app = FastAPI(title="LLM Chess Arena", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _standings_from_db(session: Session) -> list[StandingsEntry]:
    players = session.exec(select(Player)).all()
    standings: list[StandingsEntry] = []

    for player in players:
        # Hide benchmark anchor rows from standings.
        if _is_benchmark_anchor_row(player):
            continue

        games = session.exec(
            select(Game).where(
                or_(Game.white_id == player.id, Game.black_id == player.id),
                Game.status == "completed",
            )
        ).all()
        blunders = sum(
            game.white_blunders if game.white_id == player.id else game.black_blunders
            for game in games
        )
        blunder_rate = blunders / max(len(games), 1)

        standings.append(
            StandingsEntry(
                name=player.name,
                elo=round(player.elo, 1),
                elo_white=round(player.elo_white, 1),
                elo_black=round(player.elo_black, 1),
                elo_confidence=player.elo_confidence,
                elo_white_confidence=player.elo_white_confidence,
                elo_black_confidence=player.elo_black_confidence,
                elo_white_qualifying_moves=player.elo_white_qualifying_moves,
                elo_black_qualifying_moves=player.elo_black_qualifying_moves,
                wins=player.wins,
                losses=player.losses,
                draws=player.draws,
                avg_accuracy=round(player.avg_accuracy, 1),
                avg_cpl=round(player.avg_cpl, 1),
                blunder_rate=round(blunder_rate, 2),
                total_cost_usd=round(player.total_cost_usd, 4),
            )
        )

    standings.sort(key=lambda row: (-row.elo, row.name))
    return standings


def _player_name_map(session: Session, games: list[Game]) -> dict[int, str]:
    ids = set()
    for game in games:
        ids.add(game.white_id)
        ids.add(game.black_id)

    mapping: dict[int, str] = {}
    for pid in ids:
        player = session.get(Player, pid)
        if player:
            mapping[pid] = player.name
    return mapping


async def _handle_tournament_event(event: dict[str, Any]) -> None:
    runtime.live.updated_at = _now()
    runtime.live.last_event = event

    event_type = event.get("type")
    game_id = event.get("game_id")

    if event_type == "game_start" and game_id is not None:
        game_info = {
            "game_id": game_id,
            "white": event.get("white"),
            "black": event.get("black"),
            "round": event.get("round"),
        }
        runtime.live.active_games[game_id] = game_info
        runtime.live.current_game = game_info  # backward compat

    if event_type == "move" and game_id is not None:
        runtime.live.last_events[game_id] = event

    if event_type == "game_end" and game_id is not None:
        runtime.live.active_games.pop(game_id, None)
        runtime.live.last_events.pop(game_id, None)
        standings = event.get("standings", [])
        runtime.live.latest_standings = standings if isinstance(standings, list) else []
        # Update current_game to next active game or None
        if runtime.live.active_games:
            runtime.live.current_game = next(iter(runtime.live.active_games.values()))
        else:
            runtime.live.current_game = None

    await runtime.manager.broadcast(event)


def _live_response() -> LiveStateResponse:
    standings = [StandingsEntry(**entry) for entry in runtime.live.latest_standings]
    return LiveStateResponse(
        status=runtime.live.status,
        run_id=runtime.live.run_id,
        current_game=runtime.live.current_game,
        last_event=runtime.live.last_event,
        active_games=list(runtime.live.active_games.values()),
        last_events={str(k): v for k, v in runtime.live.last_events.items()},
        latest_standings=standings,
        started_at=runtime.live.started_at,
        updated_at=runtime.live.updated_at,
        error=runtime.live.error,
    )


def _build_tournament_manager(
    players: list[PlayerAdapter],
    descriptors: dict[str, dict[str, str]],
    rounds: int,
) -> TournamentManager:
    manager = TournamentManager(
        players=players,
        session_factory=_new_session,
        event_callback=_handle_tournament_event,
        rounds=rounds,
        player_descriptors=descriptors,
        settings=settings,
    )

    return manager


async def _run_tournament(
    run_id: str,
    rounds: int,
    players: list[PlayerAdapter],
    descriptors: dict[str, dict[str, str]],
) -> None:
    manager = _build_tournament_manager(players, descriptors, rounds)

    try:
        summary = await manager.run_round_robin(rounds=rounds)
        runtime.live.status = "completed"
        runtime.live.latest_standings = summary.get("standings", [])
        runtime.live.current_game = None
        runtime.live.active_games.clear()
        runtime.live.last_events.clear()
        runtime.live.last_event = {
            "type": "tournament_complete",
            "run_id": run_id,
            "games_played": summary.get("games_played", 0),
            "standings": summary.get("standings", []),
        }
        await runtime.manager.broadcast(runtime.live.last_event)
    except Exception as exc:
        runtime.live.status = "error"
        runtime.live.error = str(exc)
        runtime.live.current_game = None
        runtime.live.active_games.clear()
        runtime.live.last_events.clear()
        runtime.live.last_event = {
            "type": "tournament_error",
            "run_id": run_id,
            "error": str(exc),
        }
        await runtime.manager.broadcast(runtime.live.last_event)
        logger.exception("Tournament run failed")
    finally:
        runtime.live.updated_at = _now()
        runtime.tournament_task = None
        manager.cleanup_players(players)


async def _resume_tournament(
    run_id: str,
    tournament_id: int,
    players: list[PlayerAdapter],
    descriptors: dict[str, dict[str, str]],
    rounds: int,
) -> None:
    manager = _build_tournament_manager(players, descriptors, rounds)

    try:
        summary = await manager.resume_round_robin(tournament_id=tournament_id)
        runtime.live.status = "completed"
        runtime.live.latest_standings = summary.get("standings", [])
        runtime.live.current_game = None
        runtime.live.active_games.clear()
        runtime.live.last_events.clear()
        runtime.live.last_event = {
            "type": "tournament_complete",
            "run_id": run_id,
            "games_played": summary.get("games_played", 0),
            "standings": summary.get("standings", []),
        }
        await runtime.manager.broadcast(runtime.live.last_event)
    except Exception as exc:
        runtime.live.status = "error"
        runtime.live.error = str(exc)
        runtime.live.current_game = None
        runtime.live.active_games.clear()
        runtime.live.last_events.clear()
        runtime.live.last_event = {
            "type": "tournament_error",
            "run_id": run_id,
            "error": str(exc),
        }
        await runtime.manager.broadcast(runtime.live.last_event)
        logger.exception("Tournament resume failed")
    finally:
        runtime.live.updated_at = _now()
        runtime.tournament_task = None
        manager.cleanup_players(players)


async def _run_benchmark(
    run_id: str,
    players: list[PlayerAdapter],
    descriptors: dict[str, dict[str, str]],
) -> None:
    manager = _build_tournament_manager(players, descriptors, rounds=1)

    try:
        summary = await manager.run_benchmark()
        runtime.live.status = "completed"
        runtime.live.latest_standings = summary.get("standings", [])
        runtime.live.current_game = None
        runtime.live.active_games.clear()
        runtime.live.last_events.clear()
        runtime.live.last_event = {
            "type": "tournament_complete",
            "run_id": run_id,
            "games_played": summary.get("games_played", 0),
            "standings": summary.get("standings", []),
        }
        await runtime.manager.broadcast(runtime.live.last_event)
    except Exception as exc:
        runtime.live.status = "error"
        runtime.live.error = str(exc)
        runtime.live.current_game = None
        runtime.live.active_games.clear()
        runtime.live.last_events.clear()
        runtime.live.last_event = {
            "type": "tournament_error",
            "run_id": run_id,
            "error": str(exc),
        }
        await runtime.manager.broadcast(runtime.live.last_event)
        logger.exception("Benchmark run failed")
    finally:
        runtime.live.updated_at = _now()
        runtime.tournament_task = None
        manager.cleanup_players(players)


@app.get("/health", response_model=HealthResponse)
async def health(session: Session = Depends(get_session)) -> HealthResponse:
    db_ok = True
    try:
        session.exec(select(1)).one()
    except Exception:
        db_ok = False

    return HealthResponse(status="ok" if db_ok else "degraded", db_ok=db_ok, live_status=runtime.live.status)


@app.websocket("/ws/live")
async def live_game_ws(ws: WebSocket) -> None:
    await runtime.manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        runtime.manager.disconnect(ws)


@app.post("/api/tournament/start", response_model=TournamentStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_tournament(payload: TournamentStartRequest) -> TournamentStartResponse:
    if runtime.tournament_task and not runtime.tournament_task.done():
        raise HTTPException(status_code=409, detail="Tournament is already running")

    players, player_errors = build_players_from_settings(settings)
    if player_errors:
        logger.error(
            "Refusing tournament start because some players failed to initialize "
            "(initialized=%d configured=%d stockfish_path=%s errors=%s)",
            len(players),
            len(settings.players),
            settings.stockfish_path,
            player_errors,
        )
        detail = {
            "message": "One or more configured players failed to initialize",
            "errors": player_errors,
            "configured_players": len(settings.players),
            "initialized_players": len(players),
        }
        raise HTTPException(status_code=400, detail=detail)

    if len(players) < 2:
        detail = {
            "message": "Need at least 2 valid players to start tournament",
            "errors": player_errors,
            "configured_players": len(settings.players),
            "initialized_players": len(players),
        }
        raise HTTPException(status_code=400, detail=detail)

    run_id = uuid4().hex[:10]
    runtime.live = LiveState(
        status="running",
        run_id=run_id,
        current_game=None,
        last_event={"type": "tournament_queued", "run_id": run_id},
        latest_standings=[],
        started_at=_now(),
        updated_at=_now(),
        error=None,
    )
    player_configs = [describe_player_config(player) for player in players]

    runtime.tournament_task = asyncio.create_task(
        _run_tournament(
            run_id=run_id,
            rounds=payload.rounds,
            players=players,
            descriptors={row["name"]: row for row in player_configs},
        )
    )

    return TournamentStartResponse(
        status="accepted",
        run_id=run_id,
        rounds=payload.rounds,
        players=player_configs,
    )


@app.post("/api/tournament/resume", response_model=TournamentStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def resume_tournament(session: Session = Depends(get_session)) -> TournamentStartResponse:
    if runtime.tournament_task and not runtime.tournament_task.done():
        raise HTTPException(status_code=409, detail="Tournament is already running")

    # Find the most recent resumable tournament
    tournament = session.exec(
        select(Tournament)
        .where(Tournament.status.in_(["running", "error"]))
        .order_by(Tournament.id.desc())
    ).first()

    if tournament is None:
        raise HTTPException(status_code=404, detail="No resumable tournament found")

    stored_names: list[str] = json.loads(tournament.player_names_json)
    if not stored_names:
        raise HTTPException(status_code=400, detail="Tournament has no stored player roster")

    players, player_errors = build_players_from_settings(settings)
    if player_errors:
        logger.error(
            "Refusing tournament resume because some players failed to initialize "
            "(initialized=%d configured=%d stockfish_path=%s errors=%s)",
            len(players),
            len(settings.players),
            settings.stockfish_path,
            player_errors,
        )
        detail = {
            "message": "One or more configured players failed to initialize",
            "errors": player_errors,
            "configured_players": len(settings.players),
            "initialized_players": len(players),
        }
        raise HTTPException(status_code=400, detail=detail)

    available_names = {p.get_name() for p in players}

    missing = [name for name in stored_names if name not in available_names]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Tournament players not available: {', '.join(missing)}",
        )

    # Reorder players to match stored order
    player_map = {p.get_name(): p for p in players}
    ordered_players = [player_map[name] for name in stored_names]

    run_id = uuid4().hex[:10]
    runtime.live = LiveState(
        status="running",
        run_id=run_id,
        current_game=None,
        last_event={"type": "tournament_queued", "run_id": run_id},
        latest_standings=[],
        started_at=_now(),
        updated_at=_now(),
        error=None,
    )

    player_configs = [describe_player_config(player) for player in ordered_players]

    runtime.tournament_task = asyncio.create_task(
        _resume_tournament(
            run_id=run_id,
            tournament_id=tournament.id,
            players=ordered_players,
            descriptors={row["name"]: row for row in player_configs},
            rounds=tournament.rounds,
        )
    )

    return TournamentStartResponse(
        status="accepted",
        run_id=run_id,
        rounds=tournament.rounds,
        players=player_configs,
    )


@app.post("/api/benchmark/start", response_model=TournamentStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_benchmark() -> TournamentStartResponse:
    if runtime.tournament_task and not runtime.tournament_task.done():
        raise HTTPException(status_code=409, detail="Tournament is already running")

    # Build LLM players from settings (filter out engine-type players)
    players, player_errors = build_players_from_settings(settings)
    if player_errors:
        logger.error(
            "Refusing benchmark start because some players failed to initialize "
            "(initialized=%d configured=%d stockfish_path=%s errors=%s)",
            len(players),
            len(settings.players),
            settings.stockfish_path,
            player_errors,
        )
        detail = {
            "message": "One or more configured players failed to initialize",
            "errors": player_errors,
            "configured_players": len(settings.players),
            "initialized_players": len(players),
        }
        raise HTTPException(status_code=400, detail=detail)

    llm_players = [p for p in players if not isinstance(p, UCIEnginePlayer)]

    if not llm_players:
        raise HTTPException(status_code=400, detail="No LLM players available for benchmark")

    # Create a Stockfish player at benchmark Elo
    try:
        sf_player = UCIEnginePlayer(
            name=f"Stockfish-{settings.benchmark_stockfish_elo}",
            engine_path=settings.stockfish_path,
            time_limit=0.2,
            elo_limit=settings.benchmark_stockfish_elo,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create Stockfish player: {exc}")

    all_players: list[PlayerAdapter] = [*llm_players, sf_player]
    player_configs = [describe_player_config(p) for p in all_players]

    run_id = uuid4().hex[:10]
    runtime.live = LiveState(
        status="running",
        run_id=run_id,
        current_game=None,
        last_event={"type": "tournament_queued", "run_id": run_id},
        latest_standings=[],
        started_at=_now(),
        updated_at=_now(),
        error=None,
    )

    runtime.tournament_task = asyncio.create_task(
        _run_benchmark(
            run_id=run_id,
            players=all_players,
            descriptors={row["name"]: row for row in player_configs},
        )
    )

    return TournamentStartResponse(
        status="accepted",
        run_id=run_id,
        rounds=1,
        players=player_configs,
    )


@app.get("/api/standings", response_model=list[StandingsEntry])
async def get_standings(session: Session = Depends(get_session)) -> list[StandingsEntry]:
    return _standings_from_db(session)


@app.get("/api/games", response_model=GameListResponse)
async def list_games(limit: int = 20, offset: int = 0, session: Session = Depends(get_session)) -> GameListResponse:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    total = session.exec(
        select(func.count(Game.id)).where(Game.status == "completed")
    ).one() or 0
    games = session.exec(
        select(Game)
        .where(Game.status == "completed")
        .order_by(Game.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    ).all()
    names = _player_name_map(session, games)

    items = [
        GameSummary(
            id=game.id,
            white=names.get(game.white_id, f"player-{game.white_id}"),
            black=names.get(game.black_id, f"player-{game.black_id}"),
            result=game.result,
            termination=game.termination,
            moves_count=game.moves_count,
            white_accuracy=game.white_accuracy,
            black_accuracy=game.black_accuracy,
            duration_seconds=game.duration_seconds,
            completed_at=game.completed_at,
            opening_eco=game.opening_eco,
            opening_name=game.opening_name,
        )
        for game in games
    ]

    return GameListResponse(total=int(total), limit=safe_limit, offset=safe_offset, items=items)


@app.get("/api/games/{game_id}", response_model=GameDetail)
async def get_game(game_id: int, session: Session = Depends(get_session)) -> GameDetail:
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    white = session.get(Player, game.white_id)
    black = session.get(Player, game.black_id)

    return GameDetail(
        id=game.id,
        white=white.name if white else f"player-{game.white_id}",
        black=black.name if black else f"player-{game.black_id}",
        result=game.result,
        termination=game.termination,
        moves_count=game.moves_count,
        white_accuracy=game.white_accuracy,
        black_accuracy=game.black_accuracy,
        duration_seconds=game.duration_seconds,
        completed_at=game.completed_at,
        pgn=game.pgn,
        white_avg_cpl=game.white_avg_cpl,
        black_avg_cpl=game.black_avg_cpl,
        white_blunders=game.white_blunders,
        black_blunders=game.black_blunders,
        white_mistakes=game.white_mistakes,
        black_mistakes=game.black_mistakes,
        white_illegal_attempts=game.white_illegal_attempts,
        black_illegal_attempts=game.black_illegal_attempts,
        white_tokens=game.white_tokens,
        black_tokens=game.black_tokens,
        white_cost_usd=game.white_cost_usd,
        black_cost_usd=game.black_cost_usd,
        started_at=game.started_at,
        opening_eco=game.opening_eco,
        opening_name=game.opening_name,
    )


@app.get("/api/games/{game_id}/analysis", response_model=GameAnalysisResponse)
async def get_game_analysis(game_id: int, session: Session = Depends(get_session)) -> GameAnalysisResponse:
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    rows = session.exec(select(MoveAnalysis).where(MoveAnalysis.game_id == game_id).order_by(MoveAnalysis.id)).all()
    moves = [
        MoveAnalysisEntry(
            move_number=row.move_number,
            color=row.color,
            move_uci=row.move_uci,
            move_san=row.move_san,
            fen_before=row.fen_before,
            fen_after=row.fen_after,
            eval_before_cp=row.eval_before_cp,
            eval_after_cp=row.eval_after_cp,
            best_move_uci=row.best_move_uci,
            best_move_san=row.best_move_san,
            centipawn_loss=row.centipawn_loss,
            classification=row.classification,
            think_time_ms=row.think_time_ms,
            tokens_used=row.tokens_used,
            illegal_attempts=row.illegal_attempts,
        )
        for row in rows
    ]
    return GameAnalysisResponse(game_id=game_id, moves=moves)


@app.get("/api/players/{player_name}/stats", response_model=PlayerStats)
async def get_player_stats(player_name: str, session: Session = Depends(get_session)) -> PlayerStats:
    player = session.exec(select(Player).where(Player.name == player_name)).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    games = session.exec(
        select(Game).where(
            or_(Game.white_id == player.id, Game.black_id == player.id),
            Game.status == "completed",
        )
    ).all()
    blunders = sum(
        game.white_blunders if game.white_id == player.id else game.black_blunders
        for game in games
    )
    blunder_rate = blunders / max(len(games), 1)

    return PlayerStats(
        name=player.name,
        provider=player.provider,
        model_id=player.model_id,
        elo=round(player.elo, 1),
        elo_white=round(player.elo_white, 1),
        elo_black=round(player.elo_black, 1),
        elo_confidence=player.elo_confidence,
        elo_white_confidence=player.elo_white_confidence,
        elo_black_confidence=player.elo_black_confidence,
        elo_white_qualifying_moves=player.elo_white_qualifying_moves,
        elo_black_qualifying_moves=player.elo_black_qualifying_moves,
        games_played=player.games_played,
        wins=player.wins,
        losses=player.losses,
        draws=player.draws,
        avg_cpl=round(player.avg_cpl, 1),
        avg_accuracy=round(player.avg_accuracy, 1),
        total_tokens=player.total_tokens,
        total_cost_usd=round(player.total_cost_usd, 4),
        blunder_rate=round(blunder_rate, 2),
    )


@app.get("/api/players/{player_name}/accuracy-distribution", response_model=AccuracyDistribution)
async def get_player_accuracy_distribution(
    player_name: str, session: Session = Depends(get_session)
) -> AccuracyDistribution:
    player = session.exec(select(Player).where(Player.name == player_name)).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    games = session.exec(
        select(Game).where(
            or_(Game.white_id == player.id, Game.black_id == player.id),
            Game.status == "completed",
        )
    ).all()

    if not games:
        return AccuracyDistribution()

    game_ids = [g.id for g in games]
    color_conditions = []
    for g in games:
        if g.white_id == player.id:
            color_conditions.append(
                (MoveAnalysis.game_id == g.id) & (MoveAnalysis.color == "white")
            )
        if g.black_id == player.id:
            color_conditions.append(
                (MoveAnalysis.game_id == g.id) & (MoveAnalysis.color == "black")
            )

    moves = session.exec(
        select(MoveAnalysis).where(
            MoveAnalysis.game_id.in_(game_ids),
            or_(*color_conditions),
        )
    ).all()

    counts: dict[str, int] = {
        "best": 0, "excellent": 0, "good": 0,
        "inaccuracy": 0, "mistake": 0, "blunder": 0,
    }
    for m in moves:
        if m.classification in counts:
            counts[m.classification] += 1

    return AccuracyDistribution(
        best=counts["best"],
        excellent=counts["excellent"],
        good=counts["good"],
        inaccuracy=counts["inaccuracy"],
        mistake=counts["mistake"],
        blunder=counts["blunder"],
        total_moves=len(moves),
    )


@app.get("/api/live", response_model=LiveStateResponse)
async def get_live_state() -> LiveStateResponse:
    return _live_response()
