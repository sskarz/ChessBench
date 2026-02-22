from __future__ import annotations

from src.game.glicko2 import (
    DEFAULT_RATING,
    DEFAULT_RD,
    DEFAULT_VOLATILITY,
    Glicko2Rating,
    expected_score,
    update,
)

# Keep legacy import working so nothing breaks
from src.game.tournament import EloCalculator  # noqa: F401


def test_expected_score_is_symmetric() -> None:
    a = Glicko2Rating(1200, 100, 0.06)
    b = Glicko2Rating(1300, 100, 0.06)
    assert round(expected_score(a, b) + expected_score(b, a), 10) == 1.0


def test_equal_ratings_expect_half() -> None:
    a = Glicko2Rating(1500, 200, 0.06)
    b = Glicko2Rating(1500, 200, 0.06)
    assert round(expected_score(a, b), 6) == 0.5


def test_win_increases_rating() -> None:
    player = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    opponent = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    after = update(player, opponent, 1.0)
    assert after.rating > DEFAULT_RATING


def test_loss_decreases_rating() -> None:
    player = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    opponent = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    after = update(player, opponent, 0.0)
    assert after.rating < DEFAULT_RATING


def test_draw_at_equal_rating_stays_same() -> None:
    player = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    opponent = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    after = update(player, opponent, 0.5)
    assert abs(after.rating - DEFAULT_RATING) < 1.0


def test_rd_decreases_after_game() -> None:
    """Playing a game should reduce uncertainty (RD goes down)."""
    player = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    opponent = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    after = update(player, opponent, 1.0)
    assert after.rd < DEFAULT_RD


def test_high_rd_means_larger_rating_change() -> None:
    """A new player (high RD) should gain more points than an established one."""
    new_player = Glicko2Rating(DEFAULT_RATING, 350, DEFAULT_VOLATILITY)
    established = Glicko2Rating(DEFAULT_RATING, 50, DEFAULT_VOLATILITY)
    opponent = Glicko2Rating(DEFAULT_RATING, 100, DEFAULT_VOLATILITY)

    new_after = update(new_player, opponent, 1.0)
    est_after = update(established, opponent, 1.0)

    new_gain = new_after.rating - DEFAULT_RATING
    est_gain = est_after.rating - DEFAULT_RATING
    assert new_gain > est_gain


def test_opponent_high_rd_gives_less_info() -> None:
    """Beating an opponent with high RD (uncertain rating) should change your rating less
    than beating one with low RD (well-known rating)."""
    player = Glicko2Rating(DEFAULT_RATING, 100, DEFAULT_VOLATILITY)
    certain_opp = Glicko2Rating(DEFAULT_RATING + 200, 50, DEFAULT_VOLATILITY)
    uncertain_opp = Glicko2Rating(DEFAULT_RATING + 200, 300, DEFAULT_VOLATILITY)

    after_certain = update(player, certain_opp, 1.0)
    after_uncertain = update(player, uncertain_opp, 1.0)

    # Beating a well-known stronger player should change rating more
    gain_certain = after_certain.rating - DEFAULT_RATING
    gain_uncertain = after_uncertain.rating - DEFAULT_RATING
    assert gain_certain > gain_uncertain


def test_volatility_changes() -> None:
    """Volatility should adjust based on how unexpected the result is."""
    player = Glicko2Rating(1200, 100, DEFAULT_VOLATILITY)
    # A surprising upset: beating a much stronger player
    strong_opp = Glicko2Rating(1800, 80, DEFAULT_VOLATILITY)
    after = update(player, strong_opp, 1.0)
    # Volatility should increase because the result was unexpected
    assert after.volatility > DEFAULT_VOLATILITY


def test_convergence_over_many_games() -> None:
    """After many games, RD should converge to a small value."""
    player = Glicko2Rating(DEFAULT_RATING, DEFAULT_RD, DEFAULT_VOLATILITY)
    opponent = Glicko2Rating(DEFAULT_RATING, 100, DEFAULT_VOLATILITY)

    for _ in range(50):
        player = update(player, opponent, 0.5)

    assert player.rd < 80
