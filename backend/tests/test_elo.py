from __future__ import annotations

from src.game.tournament import EloCalculator


def test_expected_score_is_symmetric() -> None:
    a = EloCalculator.expected_score(1200, 1300)
    b = EloCalculator.expected_score(1300, 1200)
    assert round(a + b, 10) == 1.0


def test_update_for_win_and_draw() -> None:
    expected = EloCalculator.expected_score(1200, 1200)
    after_win = EloCalculator.update(1200, expected, 1.0)
    after_draw = EloCalculator.update(1200, expected, 0.5)

    assert after_win > 1200
    assert after_draw == 1200
