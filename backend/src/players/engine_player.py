from __future__ import annotations

import time

import chess
import chess.engine

from .base import MoveResult, PlayerAdapter


class UCIEnginePlayer(PlayerAdapter):
    def __init__(
        self,
        name: str,
        engine_path: str,
        time_limit: float = 0.5,
        skill_level: int | None = None,
        elo_limit: int | None = None,
    ) -> None:
        self.name = name
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.time_limit = time_limit

        if skill_level is not None:
            self.engine.configure({"Skill Level": skill_level})
        if elo_limit is not None:
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo_limit})

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        start = time.monotonic()
        result = self.engine.play(board, chess.engine.Limit(time=self.time_limit))
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return MoveResult(move=result.move, think_time_ms=elapsed_ms)

    def on_game_end(self, result: str) -> None:
        return None

    def cleanup(self) -> None:
        self.engine.quit()
