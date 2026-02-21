"""CPL-to-Elo estimation for benchmark mode.

Uses piecewise linear interpolation between empirical CPL-to-Elo data points,
with a secondary adjustment based on game result vs. the benchmark opponent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Known CPL → Elo mapping (sorted descending by CPL for interpolation)
_CPL_ELO_TABLE: list[tuple[float, float]] = [
    (300, 400),
    (200, 600),
    (120, 900),
    (80, 1200),
    (50, 1500),
    (30, 1800),
    (15, 2200),
    (5, 2600),
]

RESULT_ADJUSTMENT = 50  # added for win, subtracted for loss
DEFAULT_BENCHMARK_ELO = 1320
HIGH_CONF_WEIGHT = 1.0

Confidence = Literal["none", "low", "high"]


def _interpolate_elo(avg_cpl: float) -> float:
    """Piecewise linear interpolation from CPL to Elo."""
    if avg_cpl >= _CPL_ELO_TABLE[0][0]:
        return _CPL_ELO_TABLE[0][1]
    if avg_cpl <= _CPL_ELO_TABLE[-1][0]:
        return _CPL_ELO_TABLE[-1][1]

    for i in range(len(_CPL_ELO_TABLE) - 1):
        cpl_high, elo_low = _CPL_ELO_TABLE[i]
        cpl_low, elo_high = _CPL_ELO_TABLE[i + 1]
        if cpl_low <= avg_cpl <= cpl_high:
            t = (cpl_high - avg_cpl) / (cpl_high - cpl_low)
            return elo_low + t * (elo_high - elo_low)

    return _CPL_ELO_TABLE[0][1]


def estimate_elo_from_cpl(
    avg_cpl: float,
    game_result: str,
    opponent_elo: float = 1320,
) -> float:
    """Estimate Elo from average CPL with result adjustment.

    Args:
        avg_cpl: Filtered average centipawn loss for the player.
        game_result: "win", "loss", or "draw".
        opponent_elo: The benchmark opponent's known Elo used to shift the
                      default 1320-calibrated mapping.

    Returns:
        Estimated Elo, clamped to [200, 3000].
    """
    base_elo = _interpolate_elo(avg_cpl)

    if game_result == "win":
        base_elo += RESULT_ADJUSTMENT
    elif game_result == "loss":
        base_elo -= RESULT_ADJUSTMENT

    # Re-anchor mapping when benchmark engine is configured away from default.
    anchored_elo = base_elo + (float(opponent_elo) - DEFAULT_BENCHMARK_ELO)
    return max(200, min(3000, round(anchored_elo, 1)))


def estimate_elo_from_aggregate(
    avg_cpl: float,
    wins: int,
    draws: int,
    losses: int,
    opponent_elo: float = 1320,
) -> float:
    """Estimate Elo from aggregate CPL and win/draw/loss record.

    Uses the global average CPL (across all qualifying moves) and scales
    the result adjustment proportionally to win rate.

    Args:
        avg_cpl: Global filtered average centipawn loss across all games.
        wins: Total wins for this side.
        draws: Total draws.
        losses: Total losses.
        opponent_elo: The benchmark opponent's known Elo.

    Returns:
        Estimated Elo, clamped to [200, 3000].
    """
    base_elo = _interpolate_elo(avg_cpl)

    total = wins + draws + losses
    if total > 0:
        win_rate = (wins + draws * 0.5) / total
        # Scale from -RESULT_ADJUSTMENT (all losses) to +RESULT_ADJUSTMENT (all wins)
        base_elo += RESULT_ADJUSTMENT * (2 * win_rate - 1)

    anchored_elo = base_elo + (float(opponent_elo) - DEFAULT_BENCHMARK_ELO)
    return max(200, min(3000, round(anchored_elo, 1)))


@dataclass
class FilteredCPLResult:
    avg_cpl: float
    qualifying_moves: int
    low_confidence: bool
    has_estimate: bool


def compute_filtered_cpl(
    move_analyses: list[dict],
    color: str,
    eval_cap: int = 500,
    min_qualifying_moves: int = 5,
) -> FilteredCPLResult:
    """Compute average CPL, filtering out junk-time positions.

    Excludes moves where |eval_before_cp| > eval_cap (positions already
    decided). No unfiltered fallback is used.

    Args:
        move_analyses: List of MoveAnalysis-like dicts with at least
                       'color', 'eval_before_cp', and 'centipawn_loss'.
        color: "white" or "black" — only include moves by this player.
        eval_cap: Maximum |eval_before_cp| to include in the average.
        min_qualifying_moves: Moves needed for high confidence.

    Returns:
        FilteredCPLResult with average CPL, qualifying move count,
        and low_confidence flag.
    """
    player_moves = [m for m in move_analyses if m["color"] == color]
    if not player_moves:
        return FilteredCPLResult(
            avg_cpl=0.0,
            qualifying_moves=0,
            low_confidence=True,
            has_estimate=False,
        )

    filtered = [
        m for m in player_moves
        if m.get("eval_before_cp") is not None
        and abs(m["eval_before_cp"]) <= eval_cap
    ]

    if not filtered:
        return FilteredCPLResult(
            avg_cpl=0.0,
            qualifying_moves=0,
            low_confidence=True,
            has_estimate=False,
        )

    total_cpl = sum(m["centipawn_loss"] for m in filtered)
    return FilteredCPLResult(
        avg_cpl=total_cpl / len(filtered),
        qualifying_moves=len(filtered),
        low_confidence=len(filtered) < min_qualifying_moves,
        has_estimate=True,
    )


def confidence_from_filtered_result(result: FilteredCPLResult) -> Confidence:
    if not result.has_estimate:
        return "none"
    if result.low_confidence:
        return "low"
    return "high"


def combine_weighted_elos(
    white_elo: float | None,
    white_confidence: Confidence,
    black_elo: float | None,
    black_confidence: Confidence,
    low_conf_weight: float = 0.35,
) -> tuple[float, Confidence]:
    """Combine per-color Elo using confidence-based weights."""
    weight_map: dict[Confidence, float] = {
        "none": 0.0,
        "low": max(0.0, float(low_conf_weight)),
        "high": HIGH_CONF_WEIGHT,
    }

    weights: list[tuple[float, float]] = []
    if white_elo is not None:
        w = weight_map[white_confidence]
        if w > 0:
            weights.append((white_elo, w))
    if black_elo is not None:
        w = weight_map[black_confidence]
        if w > 0:
            weights.append((black_elo, w))

    if not weights:
        return 0.0, "none"

    total_weight = sum(w for _, w in weights)
    combined = round(sum(elo * w for elo, w in weights) / total_weight, 1)

    if white_confidence == "high" and black_confidence == "high":
        return combined, "high"
    return combined, "low"
