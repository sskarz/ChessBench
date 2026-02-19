from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

import chess
import chess.pgn

from src.analysis.analyzer import MoveEval, StockfishAnalyzer
from src.players.base import MoveResult, PlayerAdapter


@dataclass
class LiveMoveEvent:
    game_id: int
    move_number: int
    color: str
    move_uci: str
    move_san: str
    fen: str
    eval_cp: int | None
    eval_mate: int | None
    best_move_san: str | None
    cpl: int
    classification: str
    win_pct_white: float
    accuracy: float
    think_time_ms: int
    illegal_attempts: int
    white_avg_cpl: float
    black_avg_cpl: float
    pgn_so_far: str


@dataclass
class GameConfig:
    max_moves: int = 150
    analyze_depth: int = 18
    move_delay_seconds: float = 1.0


EventCallback = Callable[[LiveMoveEvent], Awaitable[None]]


class GameOrchestrator:
    def __init__(
        self,
        analyzer: StockfishAnalyzer,
        event_callback: EventCallback | None = None,
        config: GameConfig | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.event_callback = event_callback
        self.config = config or GameConfig()

    async def play_game(self, game_id: int, white: PlayerAdapter, black: PlayerAdapter) -> dict[str, Any]:
        board = chess.Board()
        game = chess.pgn.Game()
        game.headers["White"] = white.get_name()
        game.headers["Black"] = black.get_name()
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Event"] = "LLM Chess Arena"
        node = game

        white.on_game_start(chess.WHITE)
        black.on_game_start(chess.BLACK)

        move_analyses: list[dict[str, Any]] = []
        white_cpls: list[int] = []
        black_cpls: list[int] = []
        white_illegals = 0
        black_illegals = 0
        white_tokens = 0
        black_tokens = 0
        white_cost = 0.0
        black_cost = 0.0
        game_history: list[chess.Move] = []

        start_time = time.time()

        while not board.is_game_over(claim_draw=True):
            if board.fullmove_number > self.config.max_moves:
                break

            current = white if board.turn == chess.WHITE else black
            color_str = "white" if board.turn == chess.WHITE else "black"

            try:
                result: MoveResult = current.get_move(board, game_history)
            except Exception as exc:
                winner = "0-1" if board.turn == chess.WHITE else "1-0"
                game.headers["Result"] = winner
                white.on_game_end(winner)
                black.on_game_end(winner)
                return self._build_game_data(
                    game_id=game_id,
                    game=game,
                    result=winner,
                    termination=f"error:{exc}",
                    analyses=move_analyses,
                    w_cpls=white_cpls,
                    b_cpls=black_cpls,
                    w_illegals=white_illegals,
                    b_illegals=black_illegals,
                    w_tokens=white_tokens,
                    b_tokens=black_tokens,
                    w_cost=white_cost,
                    b_cost=black_cost,
                    start_time=start_time,
                    white=white,
                    black=black,
                )

            if result.move not in board.legal_moves:
                winner = "0-1" if board.turn == chess.WHITE else "1-0"
                game.headers["Result"] = winner
                white.on_game_end(winner)
                black.on_game_end(winner)
                return self._build_game_data(
                    game_id=game_id,
                    game=game,
                    result=winner,
                    termination="illegal_move",
                    analyses=move_analyses,
                    w_cpls=white_cpls,
                    b_cpls=black_cpls,
                    w_illegals=white_illegals,
                    b_illegals=black_illegals,
                    w_tokens=white_tokens,
                    b_tokens=black_tokens,
                    w_cost=white_cost,
                    b_cost=black_cost,
                    start_time=start_time,
                    white=white,
                    black=black,
                )

            if board.turn == chess.WHITE:
                white_illegals += result.illegal_attempts
                white_tokens += result.tokens_used
                white_cost += result.cost_usd
            else:
                black_illegals += result.illegal_attempts
                black_tokens += result.tokens_used
                black_cost += result.cost_usd

            move_eval: MoveEval = self.analyzer.analyze_move(board, result.move)

            if board.turn == chess.WHITE:
                white_cpls.append(move_eval.centipawn_loss)
            else:
                black_cpls.append(move_eval.centipawn_loss)

            san = board.san(result.move)
            fen_before = board.fen()
            board.push(result.move)
            fen_after = board.fen()
            node = node.add_variation(result.move)
            game_history.append(result.move)

            analysis_record = {
                "game_id": game_id,
                "move_number": board.fullmove_number - (1 if board.turn == chess.WHITE else 0),
                "color": color_str,
                "move_uci": result.move.uci(),
                "move_san": san,
                "fen_before": fen_before,
                "fen_after": fen_after,
                "eval_before_cp": move_eval.eval_before_cp,
                "eval_after_cp": move_eval.eval_after_cp,
                "best_move_uci": move_eval.best_move.uci(),
                "best_move_san": move_eval.best_move_san,
                "centipawn_loss": move_eval.centipawn_loss,
                "classification": move_eval.classification,
                "think_time_ms": result.think_time_ms,
                "tokens_used": result.tokens_used,
                "illegal_attempts": result.illegal_attempts,
            }
            move_analyses.append(analysis_record)

            if self.event_callback:
                event = LiveMoveEvent(
                    game_id=game_id,
                    move_number=len(game_history),
                    color=color_str,
                    move_uci=result.move.uci(),
                    move_san=san,
                    fen=fen_after,
                    eval_cp=move_eval.eval_after_cp,
                    eval_mate=move_eval.mate_after,
                    best_move_san=move_eval.best_move_san,
                    cpl=move_eval.centipawn_loss,
                    classification=move_eval.classification,
                    win_pct_white=(
                        move_eval.win_pct_after if board.turn == chess.BLACK else 100 - move_eval.win_pct_after
                    ),
                    accuracy=self.analyzer.move_accuracy(move_eval.centipawn_loss),
                    think_time_ms=result.think_time_ms,
                    illegal_attempts=result.illegal_attempts,
                    white_avg_cpl=sum(white_cpls) / max(len(white_cpls), 1),
                    black_avg_cpl=sum(black_cpls) / max(len(black_cpls), 1),
                    pgn_so_far=str(game),
                )
                await self.event_callback(event)

            if self.config.move_delay_seconds > 0:
                await asyncio.sleep(self.config.move_delay_seconds)

        outcome = board.outcome(claim_draw=True)
        if outcome:
            result_str = outcome.result()
            termination = outcome.termination.name.lower()
        else:
            result_str = "1/2-1/2"
            termination = "max_moves"

        game.headers["Result"] = result_str
        white.on_game_end(result_str)
        black.on_game_end(result_str)

        return self._build_game_data(
            game_id=game_id,
            game=game,
            result=result_str,
            termination=termination,
            analyses=move_analyses,
            w_cpls=white_cpls,
            b_cpls=black_cpls,
            w_illegals=white_illegals,
            b_illegals=black_illegals,
            w_tokens=white_tokens,
            b_tokens=black_tokens,
            w_cost=white_cost,
            b_cost=black_cost,
            start_time=start_time,
            white=white,
            black=black,
        )

    def _build_game_data(
        self,
        game_id: int,
        game: chess.pgn.Game,
        result: str,
        termination: str,
        analyses: list[dict[str, Any]],
        w_cpls: list[int],
        b_cpls: list[int],
        w_illegals: int,
        b_illegals: int,
        w_tokens: int,
        b_tokens: int,
        w_cost: float,
        b_cost: float,
        start_time: float,
        white: PlayerAdapter,
        black: PlayerAdapter,
    ) -> dict[str, Any]:
        def avg(values: list[float]) -> float:
            return sum(values) / max(len(values), 1)

        def game_accuracy(cpls: list[int]) -> float:
            if not cpls:
                return 0.0
            return avg([self.analyzer.move_accuracy(cpl) for cpl in cpls])

        return {
            "game_id": game_id,
            "white": white.get_name(),
            "black": black.get_name(),
            "result": result,
            "termination": termination,
            "pgn": str(game),
            "moves_count": len(analyses),
            "white_avg_cpl": round(avg([float(c) for c in w_cpls]), 1),
            "black_avg_cpl": round(avg([float(c) for c in b_cpls]), 1),
            "white_accuracy": round(game_accuracy(w_cpls), 1),
            "black_accuracy": round(game_accuracy(b_cpls), 1),
            "white_blunders": sum(1 for c in w_cpls if c > 200),
            "black_blunders": sum(1 for c in b_cpls if c > 200),
            "white_mistakes": sum(1 for c in w_cpls if 100 < c <= 200),
            "black_mistakes": sum(1 for c in b_cpls if 100 < c <= 200),
            "white_illegal_attempts": w_illegals,
            "black_illegal_attempts": b_illegals,
            "white_tokens": w_tokens,
            "black_tokens": b_tokens,
            "white_cost_usd": round(w_cost, 4),
            "black_cost_usd": round(b_cost, 4),
            "duration_seconds": round(time.time() - start_time, 1),
            "move_analyses": analyses,
        }
