from __future__ import annotations

import os
import shutil

import chess
import pytest

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
