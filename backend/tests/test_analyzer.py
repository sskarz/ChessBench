from __future__ import annotations

import chess
import chess.engine

from src.analysis.analyzer import StockfishAnalyzer


def test_classification_thresholds() -> None:
    assert StockfishAnalyzer._classify(0) == "best"
    assert StockfishAnalyzer._classify(10) == "excellent"
    assert StockfishAnalyzer._classify(30) == "good"
    assert StockfishAnalyzer._classify(100) == "inaccuracy"
    assert StockfishAnalyzer._classify(200) == "mistake"
    assert StockfishAnalyzer._classify(201) == "blunder"


def test_move_accuracy_monotonic() -> None:
    assert StockfishAnalyzer.move_accuracy(0) > StockfishAnalyzer.move_accuracy(50)
    assert StockfishAnalyzer.move_accuracy(50) > StockfishAnalyzer.move_accuracy(200)


def test_cp_to_win_pct_is_bounded() -> None:
    analyzer = object.__new__(StockfishAnalyzer)
    assert analyzer._cp_to_win_pct(None) == 50.0
    assert 0.0 <= analyzer._cp_to_win_pct(-1000) <= 100.0
    assert 0.0 <= analyzer._cp_to_win_pct(1000) <= 100.0


def test_score_to_cp_for_cp_and_mate() -> None:
    analyzer = object.__new__(StockfishAnalyzer)

    cp_score = chess.engine.PovScore(chess.engine.Cp(42), chess.WHITE)
    mate_score = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)

    assert analyzer._score_to_cp(cp_score) == 42
    assert analyzer._score_to_cp(mate_score) == 10000
