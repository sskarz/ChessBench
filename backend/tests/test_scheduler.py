from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from src.config import Settings
from src.db.models import Game, Tournament
from src.game.tournament import TournamentManager
from src.players.base import MoveResult, PlayerAdapter


class DummyPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_move(self, board, game_history) -> MoveResult:
        raise NotImplementedError


class FakeOrchestrator:
    """Unused — kept to satisfy any leftover references."""

    def __init__(self) -> None:
        self.event_callback = None
        self.on_move_recorded = None
        self.calls = 0

    async def play_game(self, game_id: int, white: PlayerAdapter, black: PlayerAdapter, resume=None) -> dict:
        self.calls += 1
        result = "1-0" if self.calls % 2 == 1 else "0-1"
        move_analyses = [
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
        ]
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
async def test_parallel_scheduler_runs_4_player_tournament(tmp_path: Path, monkeypatch) -> None:
    """With 4 players and max_concurrent=2, the scheduler should run 2 games at once."""
    session_factory = _session_factory(tmp_path / "arena_parallel.db")
    players = [DummyPlayer("A"), DummyPlayer("B"), DummyPlayer("C"), DummyPlayer("D")]
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

    # Monkeypatch StockfishAnalyzer and GameOrchestrator to avoid needing real Stockfish
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
            # Small delay to simulate work
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

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={p.get_name(): {"provider": "engine", "model": "stockfish"} for p in players},
        settings=test_settings,
    )

    summary = await manager.run_round_robin()

    # 4 players = C(4,2) = 6 pairs * 2 colors = 12 games per round
    assert summary["games_played"] == 12
    assert len([e for e in events if e["type"] == "game_start"]) == 12
    assert len([e for e in events if e["type"] == "game_end"]) == 12

    # At some point we should have had 2 concurrent games
    assert max(concurrent_games) == 2

    with session_factory() as session:
        games = session.exec(select(Game).where(Game.status == "completed")).all()
        assert len(games) == 12

        tournament = session.exec(select(Tournament)).first()
        assert tournament.status == "completed"


@pytest.mark.asyncio
async def test_parallel_scheduler_respects_max_concurrent(tmp_path: Path, monkeypatch) -> None:
    """max_concurrent_games=1 should run games sequentially."""
    session_factory = _session_factory(tmp_path / "arena_seq.db")
    players = [DummyPlayer("A"), DummyPlayer("B"), DummyPlayer("C")]
    concurrent_games: list[int] = []
    active_count = 0

    async def on_event(event: dict) -> None:
        nonlocal active_count
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
            self.on_move_recorded = None
            self.config = kwargs.get("config")
            self.analyzer = kwargs.get("analyzer")

        async def play_game(self, game_id, white, black, resume=None):
            FakeGameOrchestrator._call_counter += 1
            await asyncio.sleep(0.01)
            return {
                "game_id": game_id,
                "white": white.get_name(),
                "black": black.get_name(),
                "result": "1/2-1/2",
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

    test_settings = Settings(
        stockfish_path="/usr/local/bin/stockfish",
        max_concurrent_games=1,
        move_delay_seconds=0,
    )

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={p.get_name(): {"provider": "engine", "model": "stockfish"} for p in players},
        settings=test_settings,
    )

    summary = await manager.run_round_robin()
    assert summary["games_played"] == 6  # 3 players = 3 pairs * 2 = 6

    # With max_concurrent=1, never more than 1 game at a time
    assert max(concurrent_games) == 1


@pytest.mark.asyncio
async def test_parallel_scheduler_handles_game_error(tmp_path: Path, monkeypatch) -> None:
    """A game error should not crash the entire tournament."""
    session_factory = _session_factory(tmp_path / "arena_err.db")
    players = [DummyPlayer("A"), DummyPlayer("B")]
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

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={p.get_name(): {"provider": "engine", "model": "stockfish"} for p in players},
        settings=test_settings,
    )

    summary = await manager.run_round_robin()

    # One game errored, one succeeded
    assert summary["games_played"] == 1

    # Both games should have game_end events
    game_end_events = [e for e in events if e["type"] == "game_end"]
    assert len(game_end_events) == 2

    # The errored game should have result="*"
    error_ends = [e for e in game_end_events if e["result"] == "*"]
    assert len(error_ends) == 1
