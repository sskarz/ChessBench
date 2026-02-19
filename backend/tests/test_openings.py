"""Tests for ECO opening detection."""

from src.game.openings import detect_opening


def test_italian_game():
    pgn = '[Event "?"]\n[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bc4 *'
    eco, name = detect_opening(pgn)
    assert eco == "C50"
    assert name == "Italian Game"


def test_sicilian_defense():
    pgn = '[Event "?"]\n[Result "*"]\n\n1. e4 c5 *'
    eco, name = detect_opening(pgn)
    assert eco == "B20"
    assert name == "Sicilian Defense"


def test_sicilian_najdorf():
    pgn = '[Event "?"]\n[Result "*"]\n\n1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 *'
    eco, name = detect_opening(pgn)
    assert eco == "B90"
    assert name == "Sicilian Defense: Najdorf Variation"


def test_empty_pgn():
    eco, name = detect_opening("")
    assert eco is None
    assert name is None


def test_invalid_pgn():
    eco, name = detect_opening("not a valid pgn")
    assert eco is None
    assert name is None


def test_single_move_match():
    pgn = '[Event "?"]\n[Result "*"]\n\n1. e4 *'
    eco, name = detect_opening(pgn)
    assert eco == "B00"
    assert name == "King's Pawn Opening"


def test_longest_match_wins():
    """B92 Najdorf (11 moves with Be2) should be matched over B90 Najdorf (10 moves)."""
    pgn = '[Event "?"]\n[Result "*"]\n\n1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be2 *'
    eco, name = detect_opening(pgn)
    assert eco == "B92"
    assert name == "Sicilian Defense: Najdorf"


def test_queens_gambit_declined():
    pgn = '[Event "?"]\n[Result "*"]\n\n1. d4 d5 2. c4 e6 *'
    eco, name = detect_opening(pgn)
    assert eco == "D30"
    assert name == "Queen's Gambit Declined"


def test_ruy_lopez():
    pgn = '[Event "?"]\n[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 *'
    eco, name = detect_opening(pgn)
    assert eco == "C60"
    assert name == "Ruy Lopez"
