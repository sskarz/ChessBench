from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from src.config import Settings
from src.db.models import Game, Tournament
from src.game.tournament import BenchmarkManager
from src.players.base import MoveResult, PlayerAdapter


class DummyPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_move(self, board, game_history) -> MoveResult:
        raise NotImplementedError


def _session_factory(db_file: Path):
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)

    def _factory() -> Session:
        return Session(eng)

    return _factory


def _test_settings() -> Settings:
    """Create Settings that won't try to auto-detect stockfish."""
    return Settings(
        stockfish_path="/usr/local/bin/stockfish",
        max_concurrent_games=2,
        move_delay_seconds=0,
    )


@pytest.mark.asyncio
async def test_parallel_scheduler_runs_benchmark(tmp_path: Path, monkeypatch) -> None:
    """Benchmark with 2 LLMs + Stockfish should run 4 games (2 per LLM)."""
    session_factory = _session_factory(tmp_path / "arena_parallel.db")
    players = [DummyPlayer("A"), DummyPlayer("B"), DummyPlayer("Stockfish-800")]
    events: list[dict] = []
    concurrent_games: list[int] = []
    active_count = 0

    async def on_event(event: dict) -> None:
        nonlocal active_count
        events.append(event)
        if event["type"] == "game_start":
            active_count += 1
            concurrent_games.append(active_count)
        elif event["type"] == "game_end":
            active_count -= 1

    import src.game.scheduler as sched_mod

    class FakeAnalyzer:
        def shutdown(self):
            pass

    class FakeGameOrchestrator:
        _call_counter = 0

        def __init__(self, **kwargs):
            self.event_callback = kwargs.get("event_callback")
            self.on_move_recorded = kwargs.get("on_move_recorded") if "on_move_recorded" in kwargs else None
            self.config = kwargs.get("config")
            self.analyzer = kwargs.get("analyzer")

        async def play_game(self, game_id, white, black, resume=None):
            FakeGameOrchestrator._call_counter += 1
            await asyncio.sleep(0.01)
            result = "1-0" if FakeGameOrchestrator._call_counter % 2 == 1 else "0-1"
            move_analyses = [{
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
            }]
            if self.on_move_recorded:
                for record in move_analyses:
                    await self.on_move_recorded(game_id, record)
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
                "move_analyses": move_analyses,
            }

    monkeypatch.setattr(sched_mod, "StockfishAnalyzer", lambda **kw: FakeAnalyzer())
    monkeypatch.setattr(sched_mod, "GameOrchestrator", FakeGameOrchestrator)

    test_settings = _test_settings()

    manager = BenchmarkManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={
            "A": {"provider": "openrouter", "model": "test/a"},
            "B": {"provider": "openrouter", "model": "test/b"},
            "Stockfish-800": {"provider": "engine", "model": "stockfish"},
        },
        settings=test_settings,
    )

    summary = await manager.run_benchmark()

    # 2 LLMs * 2 games each (white + black vs Stockfish) = 4 games
    assert summary["games_played"] == 4
    assert len([e for e in events if e["type"] == "game_start"]) == 4
    assert len([e for e in events if e["type"] == "game_end"]) == 4

    # Should have had 2 concurrent games at some point
    assert max(concurrent_games) == 2

    with session_factory() as session:
        games = session.exec(select(Game).where(Game.status == "completed")).all()
        assert len(games) == 4

        tournament = session.exec(select(Tournament)).first()
        assert tournament.status == "completed"


@pytest.mark.asyncio
async def test_parallel_scheduler_handles_game_error(tmp_path: Path, monkeypatch) -> None:
    """A game error should not crash the entire benchmark."""
    session_factory = _session_factory(tmp_path / "arena_err.db")
    players = [DummyPlayer("A"), DummyPlayer("Stockfish-800")]
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    import src.game.scheduler as sched_mod

    class FakeAnalyzer:
        def shutdown(self):
            pass

    class FakeGameOrchestrator:
        _call_counter = 0

        def __init__(self, **kwargs):
            self.event_callback = kwargs.get("event_callback")
            self.on_move_recorded = None
            self.config = kwargs.get("config")
            self.analyzer = kwargs.get("analyzer")

        async def play_game(self, game_id, white, black, resume=None):
            FakeGameOrchestrator._call_counter += 1
            # First game fails, second succeeds
            if FakeGameOrchestrator._call_counter == 1:
                raise RuntimeError("Simulated game error")
            return {
                "game_id": game_id,
                "white": white.get_name(),
                "black": black.get_name(),
                "result": "1-0",
                "termination": "max_moves",
                "pgn": "1. e4 e5",
                "moves_count": 2,
                "white_avg_cpl": 20.0, "black_avg_cpl": 30.0,
                "white_accuracy": 82.0, "black_accuracy": 75.0,
                "white_blunders": 0, "black_blunders": 0,
                "white_mistakes": 0, "black_mistakes": 0,
                "white_illegal_attempts": 0, "black_illegal_attempts": 0,
                "white_tokens": 10, "black_tokens": 11,
                "white_cost_usd": 0.01, "black_cost_usd": 0.02,
                "duration_seconds": 0.5,
                "move_analyses": [],
            }

    monkeypatch.setattr(sched_mod, "StockfishAnalyzer", lambda **kw: FakeAnalyzer())
    monkeypatch.setattr(sched_mod, "GameOrchestrator", FakeGameOrchestrator)

    test_settings = _test_settings()

    manager = BenchmarkManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={
            "A": {"provider": "openrouter", "model": "test/a"},
            "Stockfish-800": {"provider": "engine", "model": "stockfish"},
        },
        settings=test_settings,
    )

    summary = await manager.run_benchmark()

    # One game errored, one succeeded
    assert summary["games_played"] == 1

    # Both games should have game_end events
    game_end_events = [e for e in events if e["type"] == "game_end"]
    assert len(game_end_events) == 2

    # The errored game should have result="*"
    error_ends = [e for e in game_end_events if e["result"] == "*"]
    assert len(error_ends) == 1
