from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from src.db.models import Game, MoveAnalysis, Player
from src.game.tournament import TournamentManager
from src.players.base import MoveResult, PlayerAdapter


class DummyPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_move(self, board, game_history) -> MoveResult:  # pragma: no cover - unused in these tests
        _ = (board, game_history)
        raise NotImplementedError


class FakeOrchestrator:
    def __init__(self) -> None:
        self.event_callback = None
        self.calls = 0

    async def play_game(self, game_id: int, white: PlayerAdapter, black: PlayerAdapter) -> dict:
        self.calls += 1
        result = "1-0" if self.calls % 2 == 1 else "0-1"

        return {
            "game_id": game_id,
            "white": white.get_name(),
            "black": black.get_name(),
            "result": result,
            "termination": "max_moves",
            "pgn": "1. e4 e5",
            "moves_count": 2,
            "white_avg_cpl": 20.0,
            "black_avg_cpl": 30.0,
            "white_accuracy": 82.0,
            "black_accuracy": 75.0,
            "white_blunders": 0,
            "black_blunders": 1,
            "white_mistakes": 0,
            "black_mistakes": 1,
            "white_illegal_attempts": 0,
            "black_illegal_attempts": 0,
            "white_tokens": 10,
            "black_tokens": 11,
            "white_cost_usd": 0.01,
            "black_cost_usd": 0.02,
            "duration_seconds": 0.5,
            "move_analyses": [
                {
                    "game_id": game_id,
                    "move_number": 1,
                    "color": "white",
                    "move_uci": "e2e4",
                    "move_san": "e4",
                    "fen_before": "start",
                    "fen_after": "after",
                    "eval_before_cp": 10,
                    "eval_after_cp": 12,
                    "best_move_uci": "e2e4",
                    "best_move_san": "e4",
                    "centipawn_loss": 0,
                    "classification": "best",
                    "think_time_ms": 15,
                    "tokens_used": 10,
                    "illegal_attempts": 0,
                }
            ],
        }


def _session_factory(db_file: Path):
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def _factory() -> Session:
        return Session(engine)

    return _factory


@pytest.mark.asyncio
async def test_tournament_manager_persists_games_and_updates_players(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Beta")]
    orchestrator = FakeOrchestrator()
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    manager = TournamentManager(
        players=players,
        orchestrator=orchestrator,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "engine", "model": "stockfish"},
            "Beta": {"provider": "engine", "model": "stockfish"},
        },
    )

    summary = await manager.run_round_robin()

    assert summary["games_played"] == 2
    assert any(event["type"] == "game_start" for event in events)
    assert any(event["type"] == "game_end" for event in events)

    with session_factory() as session:
        games = session.exec(select(Game)).all()
        moves = session.exec(select(MoveAnalysis)).all()
        db_players = session.exec(select(Player).order_by(Player.name)).all()

    assert len(games) == 2
    assert len(moves) == 2
    assert len(db_players) == 2

    alpha, beta = db_players
    assert alpha.games_played == 2
    assert beta.games_played == 2
    assert alpha.wins == 2 and alpha.losses == 0
    assert beta.wins == 0 and beta.losses == 2
    assert alpha.elo != 1200.0
    assert beta.elo != 1200.0


@pytest.mark.asyncio
async def test_tournament_manager_rejects_concurrent_run(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_lock.db")
    manager = TournamentManager(
        players=[DummyPlayer("A"), DummyPlayer("B")],
        orchestrator=FakeOrchestrator(),
        session_factory=session_factory,
    )

    async with manager._run_lock:
        with pytest.raises(RuntimeError, match="already running"):
            await manager.run_round_robin()
