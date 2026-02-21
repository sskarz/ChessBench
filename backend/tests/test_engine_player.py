from __future__ import annotations

import os
import shutil
from types import SimpleNamespace

import chess
import pytest

from src.players import engine_player
from src.players.engine_player import UCIEnginePlayer


def _stockfish_path() -> str | None:
    env_path = os.getenv("STOCKFISH_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    return shutil.which("stockfish")


def test_engine_player_returns_legal_move() -> None:
    path = _stockfish_path()
    if not path:
        pytest.skip("Stockfish binary not available")

    player = UCIEnginePlayer(name="sf", engine_path=path, time_limit=0.05)
    board = chess.Board()

    try:
        result = player.get_move(board, [])
        assert result.move in board.legal_moves
        assert result.think_time_ms >= 0
    finally:
        player.cleanup()


class _FakeEngine:
    def __init__(self, min_elo: int, max_elo: int) -> None:
        self.options = {"UCI_Elo": SimpleNamespace(min=min_elo, max=max_elo)}
        self.configure_calls: list[dict[str, int | bool]] = []

    def configure(self, options: dict[str, int | bool]) -> None:
        self.configure_calls.append(options)

    def play(self, board: chess.Board, limit: chess.engine.Limit) -> chess.engine.PlayResult:
        _ = (board, limit)
        return SimpleNamespace(move=chess.Move.from_uci("e2e4"))

    def quit(self) -> None:
        return None


def test_engine_player_clamps_elo_limit_below_supported_min(monkeypatch) -> None:
    fake_engine = _FakeEngine(min_elo=1320, max_elo=3190)
    monkeypatch.setattr(
        engine_player.chess.engine.SimpleEngine,
        "popen_uci",
        lambda _engine_path: fake_engine,
    )

    player = UCIEnginePlayer(name="sf", engine_path="/tmp/stockfish", elo_limit=800)
    try:
        assert fake_engine.configure_calls[-1] == {"UCI_LimitStrength": True, "UCI_Elo": 1320}
    finally:
        player.cleanup()


def test_engine_player_clamps_elo_limit_above_supported_max(monkeypatch) -> None:
    fake_engine = _FakeEngine(min_elo=1320, max_elo=3190)
    monkeypatch.setattr(
        engine_player.chess.engine.SimpleEngine,
        "popen_uci",
        lambda _engine_path: fake_engine,
    )

    player = UCIEnginePlayer(name="sf", engine_path="/tmp/stockfish", elo_limit=5000)
    try:
        assert fake_engine.configure_calls[-1] == {"UCI_LimitStrength": True, "UCI_Elo": 3190}
    finally:
        player.cleanup()
