from __future__ import annotations

import logging
import time

import chess
import chess.engine

from .base import MoveResult, PlayerAdapter

logger = logging.getLogger(__name__)


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
        self.engine_path = engine_path
        self.time_limit = time_limit
        self._skill_level = skill_level
        self._elo_limit = elo_limit

        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)

        if skill_level is not None:
            self.engine.configure({"Skill Level": skill_level})
        if elo_limit is not None:
            effective_elo = self._clamp_elo_limit(elo_limit)
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": effective_elo})

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        start = time.monotonic()
        result = self.engine.play(board, chess.engine.Limit(time=self.time_limit))
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return MoveResult(move=result.move, think_time_ms=elapsed_ms)

    def on_game_end(self, result: str) -> None:
        return None

    def clone(self) -> UCIEnginePlayer:
        """Create a fresh instance with the same parameters (separate engine process)."""
        return UCIEnginePlayer(
            name=self.name,
            engine_path=self.engine_path,
            time_limit=self.time_limit,
            skill_level=self._skill_level,
            elo_limit=self._elo_limit,
        )

    def cleanup(self) -> None:
        self.engine.quit()

    def _clamp_elo_limit(self, requested_elo: int) -> int:
        option = self.engine.options.get("UCI_Elo")
        if option is None:
            return requested_elo

        min_elo = getattr(option, "min", None)
        max_elo = getattr(option, "max", None)

        clamped_elo = requested_elo
        if isinstance(min_elo, int):
            clamped_elo = max(clamped_elo, min_elo)
        if isinstance(max_elo, int):
            clamped_elo = min(clamped_elo, max_elo)

        if clamped_elo != requested_elo:
            logger.warning(
                "Requested UCI_Elo=%s is out of range for %s; using %s instead.",
                requested_elo,
                self.name,
                clamped_elo,
            )
        return clamped_elo
