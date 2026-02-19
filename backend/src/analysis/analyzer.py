from __future__ import annotations

import math
from dataclasses import dataclass

import chess
import chess.engine


@dataclass
class MoveEval:
    eval_before_cp: int | None
    eval_after_cp: int | None
    mate_before: int | None
    mate_after: int | None
    best_move: chess.Move
    best_move_san: str
    centipawn_loss: int
    classification: str
    win_pct_before: float
    win_pct_after: float


class StockfishAnalyzer:
    def __init__(self, engine_path: str, depth: int = 18, threads: int = 4, hash_mb: int = 256) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.engine.configure({"Threads": threads, "Hash": hash_mb})
        self.depth = depth

    def analyze_move(self, board_before: chess.Board, move: chess.Move) -> MoveEval:
        info_before = self.engine.analyse(board_before, chess.engine.Limit(depth=self.depth))
        score_before = info_before["score"].white()

        best_result = self.engine.play(board_before, chess.engine.Limit(depth=self.depth))
        best_move = best_result.move
        best_san = board_before.san(best_move)

        board_after = board_before.copy()
        board_after.push(move)
        info_after = self.engine.analyse(board_after, chess.engine.Limit(depth=self.depth))
        score_after = info_after["score"].white()

        eval_before_cp = self._score_to_cp(score_before)
        eval_after_cp = self._score_to_cp(score_after)
        mate_before = score_before.mate() if score_before.is_mate() else None
        mate_after = score_after.mate() if score_after.is_mate() else None

        if board_before.turn == chess.WHITE:
            cpl = max(0, (eval_before_cp or 0) - (eval_after_cp or 0))
        else:
            cpl = max(0, (eval_after_cp or 0) - (eval_before_cp or 0))

        if move == best_move:
            cpl = 0

        return MoveEval(
            eval_before_cp=eval_before_cp,
            eval_after_cp=eval_after_cp,
            mate_before=mate_before,
            mate_after=mate_after,
            best_move=best_move,
            best_move_san=best_san,
            centipawn_loss=cpl,
            classification=self._classify(cpl),
            win_pct_before=self._cp_to_win_pct(eval_before_cp),
            win_pct_after=self._cp_to_win_pct(eval_after_cp),
        )

    def _score_to_cp(self, score: chess.engine.Score | chess.engine.PovScore) -> int:
        if isinstance(score, chess.engine.PovScore):
            score = score.white()
        if score.is_mate():
            mate_in = score.mate()
            return 10000 if mate_in and mate_in > 0 else -10000
        cp = score.score()
        return cp if cp is not None else 0

    def _cp_to_win_pct(self, cp: int | None) -> float:
        if cp is None:
            return 50.0
        return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)

    @staticmethod
    def _classify(cpl: int) -> str:
        if cpl == 0:
            return "best"
        if cpl <= 10:
            return "excellent"
        if cpl <= 30:
            return "good"
        if cpl <= 100:
            return "inaccuracy"
        if cpl <= 200:
            return "mistake"
        return "blunder"

    @staticmethod
    def move_accuracy(cpl: int) -> float:
        return max(0.0, 103.1668 * math.exp(-0.04354 * min(cpl, 1000)) - 3.1668)

    def shutdown(self) -> None:
        self.engine.quit()
