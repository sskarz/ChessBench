"""Glicko-2 rating system implementation.

Based on Mark Glickman's paper:
http://www.glicko.net/glicko/glicko2.pdf

Replaces the classic Elo calculator with rating deviation (RD) tracking
and volatility, giving more accurate ratings with fewer games.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Glicko-2 scale factor (converts between Glicko-1 and Glicko-2 internal scale)
SCALE = 173.7178

# System constant τ — constrains volatility change per game.
# Lower = more conservative. Glickman recommends 0.3–1.2.
# Lichess uses ~0.75. We use 0.5 for a balanced default.
TAU = 0.5

# Convergence tolerance for the volatility iteration
EPSILON = 1e-6

# Defaults
DEFAULT_RATING = 1200.0
DEFAULT_RD = 350.0
DEFAULT_VOLATILITY = 0.06


@dataclass
class Glicko2Rating:
    """A player's full Glicko-2 state."""

    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    volatility: float = DEFAULT_VOLATILITY


def _to_glicko2(rating: float, rd: float) -> tuple[float, float]:
    """Convert from Glicko-1 scale to Glicko-2 internal scale."""
    mu = (rating - DEFAULT_RATING) / SCALE
    phi = rd / SCALE
    return mu, phi


def _from_glicko2(mu: float, phi: float) -> tuple[float, float]:
    """Convert from Glicko-2 internal scale back to Glicko-1 scale."""
    rating = mu * SCALE + DEFAULT_RATING
    rd = phi * SCALE
    return rating, rd


def _g(phi: float) -> float:
    """Glicko-2 g function: reduces impact of opponents with high RD."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _E(mu: float, mu_j: float, phi_j: float) -> float:
    """Expected score against opponent j."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def update(
    player: Glicko2Rating,
    opponent: Glicko2Rating,
    score: float,
) -> Glicko2Rating:
    """Compute updated Glicko-2 rating after a single game.

    Args:
        player: Current player state.
        opponent: Opponent state.
        score: Game outcome — 1.0 (win), 0.5 (draw), 0.0 (loss).

    Returns:
        New Glicko2Rating for the player.
    """
    mu, phi = _to_glicko2(player.rating, player.rd)
    mu_j, phi_j = _to_glicko2(opponent.rating, opponent.rd)
    sigma = player.volatility

    g_j = _g(phi_j)
    E_j = _E(mu, mu_j, phi_j)

    # Step 3: Compute estimated variance
    v = 1.0 / (g_j * g_j * E_j * (1.0 - E_j))

    # Step 4: Compute estimated improvement
    delta = v * g_j * (score - E_j)

    # Step 5: Determine new volatility σ' via Illinois algorithm
    sigma_new = _new_volatility(sigma, phi, v, delta)

    # Step 6: Update RD to new pre-rating period value
    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)

    # Step 7: Update rating and RD
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * g_j * (score - E_j)

    rating_new, rd_new = _from_glicko2(mu_new, phi_new)

    return Glicko2Rating(
        rating=round(rating_new, 1),
        rd=round(rd_new, 1),
        volatility=sigma_new,
    )


def _new_volatility(
    sigma: float, phi: float, v: float, delta: float
) -> float:
    """Compute new volatility using the Illinois algorithm (Glickman Step 5)."""
    a = math.log(sigma * sigma)
    tau_sq = TAU * TAU
    phi_sq = phi * phi
    delta_sq = delta * delta

    def f(x: float) -> float:
        ex = math.exp(x)
        denom = phi_sq + v + ex
        term1 = (ex * (delta_sq - phi_sq - v - ex)) / (2.0 * denom * denom)
        term2 = (x - a) / tau_sq
        return term1 - term2

    # Initial bounds
    A = a
    if delta_sq > phi_sq + v:
        B = math.log(delta_sq - phi_sq - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        B = a - k * TAU

    f_A = f(A)
    f_B = f(B)

    # Illinois algorithm iteration
    while abs(B - A) > EPSILON:
        C = A + (A - B) * f_A / (f_B - f_A)
        f_C = f(C)

        if f_C * f_B <= 0:
            A = B
            f_A = f_B
        else:
            f_A /= 2.0

        B = C
        f_B = f_C

    return math.exp(A / 2.0)


def expected_score(
    player: Glicko2Rating, opponent: Glicko2Rating
) -> float:
    """Return the expected score for player against opponent (0.0 – 1.0)."""
    mu, _ = _to_glicko2(player.rating, player.rd)
    mu_j, phi_j = _to_glicko2(opponent.rating, opponent.rd)
    return _E(mu, mu_j, phi_j)
