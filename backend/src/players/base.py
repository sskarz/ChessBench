from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import chess


@dataclass
class MoveResult:
    move: chess.Move
    tokens_used: int = 0
    cost_usd: float = 0.0
    think_time_ms: int = 0
    illegal_attempts: int = 0
    raw_response: str = ""


class PlayerAdapter(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """Stable player name used in PGN and stats."""

    @abstractmethod
    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        """Return the next legal move for the current position."""

    def on_game_start(self, color: chess.Color) -> None:
        """Called before game begins."""

    def on_game_end(self, result: str) -> None:
        """Called after game ends."""
