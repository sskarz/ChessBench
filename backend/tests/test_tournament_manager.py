from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from src.config import Settings
from src.db.models import Game, MoveAnalysis, Player, Tournament
from src.game.tournament import TournamentManager, _generate_pairing_schedule
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
async def test_tournament_manager_persists_games_and_updates_players(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Beta")]
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        event_callback=on_event,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "engine", "model": "stockfish"},
            "Beta": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    summary = await manager.run_round_robin()

    assert summary["games_played"] == 2
    assert any(event["type"] == "game_start" for event in events)
    assert any(event["type"] == "game_end" for event in events)

    with session_factory() as session:
        games = session.exec(select(Game).where(Game.status == "completed")).all()
        moves = session.exec(select(MoveAnalysis)).all()
        db_players = session.exec(select(Player).order_by(Player.name)).all()

    assert len(games) == 2
    assert len(moves) == 2
    assert len(db_players) == 2

    alpha, beta = db_players
    assert alpha.games_played == 2
    assert beta.games_played == 2
    assert alpha.elo != 1200.0
    assert beta.elo != 1200.0


@pytest.mark.asyncio
async def test_tournament_manager_creates_tournament_record(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_tournament.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Beta")]

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "engine", "model": "stockfish"},
            "Beta": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    await manager.run_round_robin()

    with session_factory() as session:
        tournaments = session.exec(select(Tournament)).all()
        assert len(tournaments) == 1
        t = tournaments[0]
        assert t.status == "completed"
        assert t.rounds == 1
        assert json.loads(t.player_names_json) == ["Alpha", "Beta"]
        assert t.completed_at is not None

        # All games should be completed and have tournament_id
        games = session.exec(select(Game).where(Game.status == "completed")).all()
        assert all(g.tournament_id == t.id for g in games)
        assert all(g.pairing_index is not None for g in games)


@pytest.mark.asyncio
async def test_tournament_manager_rejects_concurrent_run(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path / "arena_lock.db")
    manager = TournamentManager(
        players=[DummyPlayer("A"), DummyPlayer("B")],
        session_factory=session_factory,
        settings=_test_settings(),
    )

    async with manager._run_lock:
        with pytest.raises(RuntimeError, match="already running"):
            await manager.run_round_robin()


@pytest.mark.asyncio
async def test_tournament_resume_skips_completed_games(tmp_path: Path) -> None:
    """Resume should skip already-completed games and only play remaining ones."""
    session_factory = _session_factory(tmp_path / "arena_resume.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Beta")]

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "engine", "model": "stockfish"},
            "Beta": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    # Run a full tournament first
    await manager.run_round_robin()

    with session_factory() as session:
        tournament = session.exec(select(Tournament)).first()
        assert tournament is not None
        tournament_id = tournament.id

        # Simulate an interrupted state: set tournament back to "running"
        # and mark the second game as "in_progress" (simulating crash mid-game)
        tournament.status = "running"
        tournament.completed_at = None
        games = session.exec(select(Game).order_by(Game.id)).all()
        assert len(games) == 2
        # Keep first game completed, revert second to in_progress
        games[1].status = "in_progress"
        games[1].result = "*"
        session.commit()

    manager2 = TournamentManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "engine", "model": "stockfish"},
            "Beta": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    summary = await manager2.resume_round_robin(tournament_id=tournament_id)

    # Should have only played 1 game (the resumed in-progress one)
    assert summary["games_played"] == 1

    with session_factory() as session:
        tournament = session.get(Tournament, tournament_id)
        assert tournament.status == "completed"
        games = session.exec(select(Game).where(Game.status == "completed")).all()
        assert len(games) == 2


@pytest.mark.asyncio
async def test_tournament_resume_reuses_existing_in_progress_rows(tmp_path: Path) -> None:
    """Resume should not duplicate rows when multiple games are still in progress."""
    session_factory = _session_factory(tmp_path / "arena_resume_multi.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Beta"), DummyPlayer("Gamma")]

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={name: {"provider": "engine", "model": "stockfish"} for name in ["Alpha", "Beta", "Gamma"]},
        settings=_test_settings(),
    )

    # Run a full tournament first (3 players => 6 games).
    await manager.run_round_robin()

    with session_factory() as session:
        tournament = session.exec(select(Tournament)).first()
        assert tournament is not None
        tournament_id = tournament.id
        tournament.status = "running"
        tournament.completed_at = None

        games = session.exec(
            select(Game)
            .where(Game.tournament_id == tournament_id)
            .order_by(Game.id)
        ).all()
        assert len(games) == 6
        assert all(g.pairing_index is not None for g in games)

        # Simulate interruption with multiple pending in-progress rows.
        for game in games[3:]:
            game.status = "in_progress"
            game.result = "*"
            game.completed_at = None

        original_ids_by_pairing = {g.pairing_index: g.id for g in games}
        session.commit()

    manager2 = TournamentManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={name: {"provider": "engine", "model": "stockfish"} for name in ["Alpha", "Beta", "Gamma"]},
        settings=_test_settings(),
    )

    summary = await manager2.resume_round_robin(tournament_id=tournament_id)
    assert summary["games_played"] == 3

    with session_factory() as session:
        games = session.exec(
            select(Game)
            .where(Game.tournament_id == tournament_id)
            .order_by(Game.id)
        ).all()
        assert len(games) == 6
        assert all(g.status == "completed" for g in games)

        by_pairing: dict[int | None, list[int]] = {}
        for game in games:
            by_pairing.setdefault(game.pairing_index, []).append(game.id)
        assert all(len(ids) == 1 for ids in by_pairing.values())

        final_ids_by_pairing = {g.pairing_index: g.id for g in games}
        assert final_ids_by_pairing == original_ids_by_pairing


def test_pairing_schedule_deterministic() -> None:
    """Pairing schedule should be deterministic for the same inputs."""
    s1 = _generate_pairing_schedule(3, 2)
    s2 = _generate_pairing_schedule(3, 2)
    assert s1 == s2
    # 3 players = 3 pairs, each plays as white/black = 6 games per round, 2 rounds = 12
    assert len(s1) == 12


@pytest.mark.asyncio
async def test_get_standings_filters_completed_only(tmp_path: Path) -> None:
    """get_standings should only count completed games for blunder_rate."""
    session_factory = _session_factory(tmp_path / "arena_standings.db")
    players = [DummyPlayer("Alpha"), DummyPlayer("Beta")]

    manager = TournamentManager(
        players=players,
        session_factory=session_factory,
        rounds=1,
        player_descriptors={
            "Alpha": {"provider": "engine", "model": "stockfish"},
            "Beta": {"provider": "engine", "model": "stockfish"},
        },
        settings=_test_settings(),
    )

    await manager.run_round_robin()

    # Add an in-progress game that should be excluded from standings
    with session_factory() as session:
        alpha = session.exec(select(Player).where(Player.name == "Alpha")).first()
        beta = session.exec(select(Player).where(Player.name == "Beta")).first()
        session.add(Game(
            id=999,
            white_id=alpha.id,
            black_id=beta.id,
            status="in_progress",
            white_blunders=100,
            black_blunders=100,
        ))
        session.commit()

    with session_factory() as session:
        standings = manager.get_standings(session=session)

    # The in-progress game's 100 blunders should not affect blunder_rate
    for entry in standings:
        assert entry["blunder_rate"] < 50
