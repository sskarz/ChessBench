from __future__ import annotations

from dataclasses import dataclass

import chess
import pytest

from src.analysis.analyzer import MoveEval
from src.game.orchestrator import GameConfig, GameOrchestrator
from src.players.base import MoveResult, PlayerAdapter


@dataclass
class FakeAnalyzer:
    cpl: int = 12

    def analyze_move(self, board_before: chess.Board, move: chess.Move) -> MoveEval:
        return MoveEval(
            eval_before_cp=10,
            eval_after_cp=8,
            mate_before=None,
            mate_after=None,
            best_move=move,
            best_move_san=board_before.san(move),
            centipawn_loss=self.cpl,
            classification="good",
            win_pct_before=50.0,
            win_pct_after=49.0,
        )

    @staticmethod
    def move_accuracy(cpl: int) -> float:
        return max(0.0, 100.0 - cpl / 2)


class FirstLegalPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self.name = name

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        _ = game_history
        return MoveResult(move=next(iter(board.legal_moves)))


class CrashPlayer(PlayerAdapter):
    def __init__(self, name: str) -> None:
        self.name = name

    def get_name(self) -> str:
        return self.name

    def get_move(self, board: chess.Board, game_history: list[chess.Move]) -> MoveResult:
        _ = (board, game_history)
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_orchestrator_runs_and_returns_expected_shape() -> None:
    events = []

    async def callback(event) -> None:
        events.append(event)

    orchestrator = GameOrchestrator(
        analyzer=FakeAnalyzer(),
        event_callback=callback,
        config=GameConfig(max_moves=1, move_delay_seconds=0.0),
    )

    result = await orchestrator.play_game(
        game_id=7,
        white=FirstLegalPlayer("white"),
        black=FirstLegalPlayer("black"),
    )

    assert result["game_id"] == 7
    assert result["termination"] == "max_moves"
    assert result["moves_count"] == 2
    assert len(result["move_analyses"]) == 2
    assert "1." in result["pgn"]
    assert len(events) == 2
    assert [event.eval_cp for event in events] == [8, 8]
    assert [event.win_pct_white for event in events] == [49.0, 49.0]


@pytest.mark.asyncio
async def test_orchestrator_player_error_awards_opponent() -> None:
    orchestrator = GameOrchestrator(
        analyzer=FakeAnalyzer(),
        config=GameConfig(max_moves=1, move_delay_seconds=0.0),
    )

    result = await orchestrator.play_game(
        game_id=8,
        white=CrashPlayer("crash"),
        black=FirstLegalPlayer("stable"),
    )

    assert result["result"] == "0-1"
    assert result["termination"].startswith("error:")
    assert result["moves_count"] == 0
