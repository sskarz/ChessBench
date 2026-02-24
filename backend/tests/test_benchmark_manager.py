from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from src.config import Settings
from src.db.models import Game, MoveAnalysis, Player, Tournament
from src.game.tournament import BenchmarkManager
from src.players.base import MoveResult, PlayerAdapter


class DummyPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_move(self, board, game_history) -> MoveResult:  # pragma: no cover - unused in these tests
        _ = (board, game_history)
        raise NotImplementedError


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

    async def play_game(self, game_id: int, white: PlayerAdapter, black: PlayerAdapter, resume=None) -> dict:
        FakeGameOrchestrator._call_counter += 1
        result = "1-0" if FakeGameOrchestrator._call_counter % 2 == 1 else "0-1"

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

        # Simulate per-move persistence like the real orchestrator
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
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def _factory() -> Session:
        return Session(engine)

    return _factory


def _test_settings() -> Settings:
    return Settings(
        stockfish_path="/usr/local/bin/stockfish",
        max_concurrent_games=1,
        move_delay_seconds=0,
    )


@pytest.fixture(autouse=True)
def _patch_scheduler(monkeypatch):
    """Monkeypatch the scheduler to use fakes instead of real Stockfish."""
    import src.game.scheduler as sched_mod
    FakeGameOrchestrator._call_counter = 0
    monkeypatch.setattr(sched_mod, "StockfishAnalyzer", lambda **kw: FakeAnalyzer())
    monkeypatch.setattr(sched_mod, "GameOrchestrator", FakeGameOrchestrator)


@pytest.mark.asyncio
async def test_benchmark_manager_persists_games_and_updates_players(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena.db")
    # Benchmark requires an engine player + at least one LLM player
    players = [DummyPlayer("Alpha"), DummyPlayer("Stockfish-800")]
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    manager = BenchmarkManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "openrouter", "model": "test/alpha"},
            "Stockfish-800": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    summary = await manager.run_benchmark()

    assert summary["games_played"] == 2  # 1 LLM * 2 games (white + black)
    assert any(event["type"] == "game_start" for event in events)
    assert any(event["type"] == "game_end" for event in events)

    with session_factory() as session:
        games = session.exec(select(Game).where(Game.status == "completed")).all()
        moves = session.exec(select(MoveAnalysis)).all()
        db_players = session.exec(select(Player).order_by(Player.name)).all()

    assert len(games) == 2
    assert len(moves) == 2
    assert len(db_players) == 2

    alpha = next(p for p in db_players if p.name == "Alpha")
    assert alpha.games_played == 2


@pytest.mark.asyncio
async def test_benchmark_manager_creates_tournament_record(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_benchmark.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Stockfish-800")]

    manager = BenchmarkManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "openrouter", "model": "test/alpha"},
            "Stockfish-800": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    await manager.run_benchmark()

    with session_factory() as session:
        tournaments = session.exec(select(Tournament)).all()
        assert len(tournaments) == 1
        t = tournaments[0]
        assert t.status == "completed"
        assert t.format == "benchmark"
        assert t.rounds == 1
        assert t.completed_at is not None


@pytest.mark.asyncio
async def test_benchmark_manager_rejects_concurrent_run(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_lock.db")
    manager = BenchmarkManager(
        players=[DummyPlayer("A"), DummyPlayer("SF")],
        session_factory=session_factory,
        player_descriptors={
            "A": {"provider": "openrouter", "model": "test/a"},
            "SF": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    async with manager._run_lock:
        with pytest.raises(RuntimeError, match="already running"):
            await manager.run_benchmark()


def test_get_standings_returns_sorted_by_elo(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_sort.db")
    manager = BenchmarkManager(
        players=[],
        session_factory=session_factory,
        settings=_test_settings(),
    )

    with session_factory() as session:
        session.add(Player(name="Alpha", provider="openrouter", model_id="a", elo=1200.0))
        session.add(Player(name="Beta", provider="openrouter", model_id="b", elo=1600.0))
        session.commit()

    with session_factory() as session:
        standings = manager.get_standings(session=session)

    assert standings[0]["name"] == "Beta"
    assert standings[1]["name"] == "Alpha"


def test_get_standings_hides_benchmark_anchor(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_anchor.db")
    manager = BenchmarkManager(
        players=[],
        session_factory=session_factory,
        settings=_test_settings(),
    )

    with session_factory() as session:
        session.add(Player(name="Alpha", provider="openrouter", model_id="a", elo=1200.0))
        session.add(Player(name="Stockfish-800", provider="engine", model_id="stockfish", elo=800.0))
        session.commit()

    with session_factory() as session:
        standings = manager.get_standings(session=session)

    names = [s["name"] for s in standings]
    assert "Alpha" in names
    assert "Stockfish-800" not in names
