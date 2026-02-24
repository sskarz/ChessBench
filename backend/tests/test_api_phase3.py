from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from src.api import server
from src.api.server import LiveState, app
from src.db.models import Game, MoveAnalysis, Player, Tournament
from src.db.session import get_session
from src.players.base import MoveResult, PlayerAdapter


class DummyPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_move(self, board, game_history) -> MoveResult:
        _ = (board, game_history)
        raise NotImplementedError


class DummyTask:
    def __init__(self, is_done: bool) -> None:
        self._is_done = is_done

    def done(self) -> bool:
        return self._is_done


def _build_test_engine(db_file: Path):
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_data(engine) -> None:
    with Session(engine) as session:
        alpha = Player(name="Alpha", provider="openrouter", model_id="test/alpha", elo=1210.5, games_played=1, wins=1)
        beta = Player(name="Beta", provider="openrouter", model_id="test/beta", elo=1189.5, games_played=1, losses=1)
        session.add(alpha)
        session.add(beta)
        session.commit()
        session.refresh(alpha)
        session.refresh(beta)

        game = Game(
            id=1,
            white_id=alpha.id,
            black_id=beta.id,
            status="completed",
            result="1-0",
            termination="checkmate",
            pgn="1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#",
            moves_count=7,
            white_avg_cpl=18.2,
            black_avg_cpl=70.5,
            white_accuracy=88.1,
            black_accuracy=61.0,
            white_blunders=0,
            black_blunders=2,
            white_mistakes=0,
            black_mistakes=1,
            white_illegal_attempts=0,
            black_illegal_attempts=1,
            white_tokens=15,
            black_tokens=20,
            white_cost_usd=0.01,
            black_cost_usd=0.02,
            duration_seconds=12.5,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        session.add(game)
        session.add(
            MoveAnalysis(
                game_id=1,
                move_number=1,
                color="white",
                move_uci="e2e4",
                move_san="e4",
                fen_before="start",
                fen_after="after",
                eval_before_cp=20,
                eval_after_cp=22,
                best_move_uci="e2e4",
                best_move_san="e4",
                centipawn_loss=0,
                classification="best",
                think_time_ms=20,
                tokens_used=5,
                illegal_attempts=0,
            )
        )
        session.commit()


def _client_with_seeded_db(tmp_path: Path) -> Generator[TestClient, None, None]:
    engine = _build_test_engine(tmp_path / "api.db")
    _seed_data(engine)

    def _override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None


def test_api_read_endpoints(tmp_path: Path) -> None:
    for client in _client_with_seeded_db(tmp_path):
        standings = client.get("/api/standings")
        assert standings.status_code == 200
        assert standings.json()[0]["name"] == "Alpha"

        games = client.get("/api/games?limit=20&offset=0")
        assert games.status_code == 200
        payload = games.json()
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == 1

        game = client.get("/api/games/1")
        assert game.status_code == 200
        assert game.json()["result"] == "1-0"

        analysis = client.get("/api/games/1/analysis")
        assert analysis.status_code == 200
        assert len(analysis.json()["moves"]) == 1

        player = client.get("/api/players/Alpha/stats")
        assert player.status_code == 200
        assert player.json()["wins"] == 1

        not_found = client.get("/api/games/999")
        assert not_found.status_code == 404


def test_api_live_endpoint(tmp_path: Path) -> None:
    for client in _client_with_seeded_db(tmp_path):
        server.runtime.live = LiveState(
            status="running",
            run_id="run-123",
            current_game={"game_id": 1, "white": "Alpha", "black": "Beta", "round": 1},
            last_event={"type": "game_start", "game_id": 1},
            latest_standings=[],
            started_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            error=None,
        )
        response = client.get("/api/live")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert response.json()["run_id"] == "run-123"


def test_benchmark_start_endpoint_rejects_partial_roster(monkeypatch) -> None:
    monkeypatch.setattr(server, "init_db", lambda: None)

    players = [DummyPlayer("A"), DummyPlayer("B"), DummyPlayer("C")]
    errors = ["Failed to build player 'Broken'"]
    monkeypatch.setattr(server, "build_players_from_settings", lambda _settings: (players, errors))

    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None

    with TestClient(app) as client:
        response = client.post("/api/benchmark/start")
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["message"] == "One or more configured players failed to initialize"
        assert detail["errors"] == errors
        assert detail["configured_players"] >= 3
        assert detail["initialized_players"] == 3

    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None


def test_standings_hide_benchmark_anchor_only(tmp_path: Path) -> None:
    engine = _build_test_engine(tmp_path / "anchor.db")
    _seed_data(engine)

    with Session(engine) as session:
        session.add(Player(name="Engine Rival", provider="engine", model_id="lc0", elo=1300.0))
        session.add(Player(name="Stockfish-1320", provider="engine", model_id="stockfish", elo=1200.0))
        session.commit()

    def _override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None

    with TestClient(app) as client:
        standings = client.get("/api/standings")
        assert standings.status_code == 200
        names = {row["name"] for row in standings.json()}
        assert "Engine Rival" in names
        assert "Stockfish-1320" not in names

    app.dependency_overrides.clear()
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None


def test_standings_blunder_rate_from_total_blunders(tmp_path: Path) -> None:
    engine = _build_test_engine(tmp_path / "standings_blunder.db")

    with Session(engine) as session:
        alpha = Player(
            name="Alpha",
            provider="openrouter",
            model_id="alpha",
            elo=1400.0,
            games_played=2,
            total_blunders=1,
        )
        beta = Player(
            name="Beta",
            provider="openrouter",
            model_id="beta",
            elo=1300.0,
            games_played=2,
            total_blunders=4,
        )
        session.add(alpha)
        session.add(beta)
        session.commit()

    def _override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None

    with TestClient(app) as client:
        rows = client.get("/api/standings")
        assert rows.status_code == 200
        data = rows.json()

        alpha_row = next(row for row in data if row["name"] == "Alpha")
        beta_row = next(row for row in data if row["name"] == "Beta")
        assert alpha_row["blunder_rate"] == 0.5
        assert beta_row["blunder_rate"] == 2.0

    app.dependency_overrides.clear()
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None


def test_accuracy_distribution_returns_all_games(tmp_path: Path) -> None:
    engine = _build_test_engine(tmp_path / "accuracy.db")

    with Session(engine) as session:
        bm = Tournament(name="BM", format="benchmark", rounds=1, status="completed")
        session.add(bm)
        session.commit()
        session.refresh(bm)

        alpha = Player(name="Alpha", provider="openrouter", model_id="alpha")
        beta = Player(name="Beta", provider="openrouter", model_id="beta")
        session.add(alpha)
        session.add(beta)
        session.commit()
        session.refresh(alpha)
        session.refresh(beta)

        session.add(Game(id=1, tournament_id=bm.id, white_id=alpha.id, black_id=beta.id, status="completed"))
        session.add(
            MoveAnalysis(
                game_id=1,
                move_number=1,
                color="white",
                move_uci="e2e4",
                move_san="e4",
                fen_before="start",
                fen_after="after",
                centipawn_loss=0,
                classification="best",
            )
        )
        session.add(
            MoveAnalysis(
                game_id=1,
                move_number=1,
                color="black",
                move_uci="e7e5",
                move_san="e5",
                fen_before="start",
                fen_after="after",
                centipawn_loss=120,
                classification="blunder",
            )
        )
        session.commit()

    def _override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None

    with TestClient(app) as client:
        response = client.get("/api/players/Alpha/accuracy-distribution")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_moves"] == 1
        assert payload["best"] == 1
        assert payload["blunder"] == 0

    app.dependency_overrides.clear()
    server.runtime.live = LiveState(updated_at=datetime.utcnow())
    server.runtime.benchmark_task = None
