from __future__ import annotations

from src.analysis.elo_estimator import (
    combine_weighted_elos,
    compute_filtered_cpl,
    confidence_from_filtered_result,
    estimate_elo_from_cpl,
)


def test_estimate_elo_uses_default_anchor_without_shift() -> None:
    assert estimate_elo_from_cpl(avg_cpl=120, game_result="draw", opponent_elo=1320) == 900.0


def test_estimate_elo_applies_result_adjustment() -> None:
    draw_elo = estimate_elo_from_cpl(avg_cpl=80, game_result="draw")
    win_elo = estimate_elo_from_cpl(avg_cpl=80, game_result="win")
    loss_elo = estimate_elo_from_cpl(avg_cpl=80, game_result="loss")

    assert draw_elo == 1200.0
    assert win_elo == draw_elo + 50
    assert loss_elo == draw_elo - 50


def test_estimate_elo_shifts_with_configured_anchor() -> None:
    # 120 CPL -> 900 base Elo. Anchor at 1500 adds +180 over default 1320.
    assert estimate_elo_from_cpl(avg_cpl=120, game_result="draw", opponent_elo=1500) == 1080.0


def test_compute_filtered_cpl_uses_filtered_subset_when_enough_moves() -> None:
    moves = [
        {"color": "white", "eval_before_cp": 0, "centipawn_loss": 10},
        {"color": "white", "eval_before_cp": 100, "centipawn_loss": 20},
        {"color": "white", "eval_before_cp": -200, "centipawn_loss": 30},
        {"color": "white", "eval_before_cp": 300, "centipawn_loss": 40},
        {"color": "white", "eval_before_cp": 500, "centipawn_loss": 50},
        {"color": "white", "eval_before_cp": 900, "centipawn_loss": 999},
    ]

    result = compute_filtered_cpl(moves, "white", eval_cap=500)

    assert result.low_confidence is False
    assert result.qualifying_moves == 5
    assert result.has_estimate is True
    assert result.avg_cpl == 30.0


def test_compute_filtered_cpl_marks_low_confidence_when_too_few_moves() -> None:
    moves = [
        {"color": "black", "eval_before_cp": 900, "centipawn_loss": 100},
        {"color": "black", "eval_before_cp": -850, "centipawn_loss": 200},
        {"color": "black", "eval_before_cp": 100, "centipawn_loss": 20},
        {"color": "black", "eval_before_cp": None, "centipawn_loss": 30},
    ]

    result = compute_filtered_cpl(moves, "black", eval_cap=500)

    assert result.low_confidence is True
    assert result.qualifying_moves == 1
    assert result.has_estimate is True
    assert result.avg_cpl == 20.0


def test_compute_filtered_cpl_returns_no_estimate_when_no_qualifying_moves() -> None:
    moves = [
        {"color": "black", "eval_before_cp": 900, "centipawn_loss": 100},
        {"color": "black", "eval_before_cp": -850, "centipawn_loss": 200},
    ]

    result = compute_filtered_cpl(moves, "black", eval_cap=500)

    assert result.low_confidence is True
    assert result.qualifying_moves == 0
    assert result.has_estimate is False
    assert result.avg_cpl == 0.0


def test_confidence_from_filtered_result() -> None:
    no_estimate = compute_filtered_cpl(
        [{"color": "white", "eval_before_cp": 700, "centipawn_loss": 15}],
        "white",
        eval_cap=500,
    )
    low = compute_filtered_cpl(
        [{"color": "white", "eval_before_cp": 100, "centipawn_loss": 15}],
        "white",
        eval_cap=500,
    )
    high = compute_filtered_cpl(
        [
            {"color": "white", "eval_before_cp": 0, "centipawn_loss": 10},
            {"color": "white", "eval_before_cp": 10, "centipawn_loss": 10},
            {"color": "white", "eval_before_cp": 20, "centipawn_loss": 10},
            {"color": "white", "eval_before_cp": 30, "centipawn_loss": 10},
            {"color": "white", "eval_before_cp": 40, "centipawn_loss": 10},
        ],
        "white",
        eval_cap=500,
    )

    assert confidence_from_filtered_result(no_estimate) == "none"
    assert confidence_from_filtered_result(low) == "low"
    assert confidence_from_filtered_result(high) == "high"


def test_combine_weighted_elos() -> None:
    combined, conf = combine_weighted_elos(white_elo=1500, white_confidence="high", black_elo=1300, black_confidence="low")
    assert combined == 1448.1
    assert conf == "low"

    combined, conf = combine_weighted_elos(white_elo=1500, white_confidence="high", black_elo=1300, black_confidence="high")
    assert combined == 1400.0
    assert conf == "high"

    combined, conf = combine_weighted_elos(white_elo=None, white_confidence="none", black_elo=None, black_confidence="none")
    assert combined == 0.0
    assert conf == "none"
