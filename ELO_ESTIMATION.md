# Elo Estimation: How Benchmark Mode Works

ChessBench uses two distinct Elo systems depending on the mode:

1. **Round-Robin Elo** — traditional win/loss Elo (K=32) from head-to-head LLM games
2. **Benchmark Elo** — CPL-based estimation from games against a calibrated Stockfish anchor

This document describes the benchmark system.

---

## Overview

Each LLM plays **2 games** against Stockfish-1320 (one as white, one as black). Instead of relying solely on win/loss outcomes — which are noisy with only 2 games — the system estimates Elo from **average centipawn loss (CPL)**, the most reliable per-game measure of playing strength.

Stockfish at Elo 1320 serves as the **calibrated anchor**. Its known rating grounds the estimation so that results are comparable across runs without needing a large tournament pool.

## Step 1: Filtered CPL Calculation

After a game completes, the system computes the LLM's average CPL with **junk-time filtering**:

1. Collect all moves played by the LLM in that game
2. **Exclude** any move where `|eval_before_cp| > 500` (positions already decisively won or lost — moves here don't reflect true skill)
3. Average the remaining centipawn loss values

If fewer than 5 moves survive the filter (e.g., a very short game), the system falls back to unfiltered CPL and flags the result as `low_confidence`.

**Why filter?** In lost positions (e.g., down a queen), even random moves have high CPL that doesn't reflect the player's actual ability. Filtering these out produces a more accurate skill estimate.

## Step 2: CPL-to-Elo Interpolation

The filtered average CPL maps to an estimated Elo via **piecewise linear interpolation** between empirically-derived data points:

| Avg CPL | Estimated Elo |
|---------|---------------|
| 300+    | 400           |
| 200     | 600           |
| 120     | 900           |
| 80      | 1200          |
| 50      | 1500          |
| 30      | 1800          |
| 15      | 2200          |
| 5       | 2600          |

For CPL values between data points, the system interpolates linearly. For example:

- CPL 65 falls between 80 (Elo 1200) and 50 (Elo 1500) → interpolated to ~1350
- CPL 10 falls between 15 (Elo 2200) and 5 (Elo 2600) → interpolated to ~2400

These anchor points are derived from large-scale analysis of human games at known rating levels on Lichess.

## Step 3: Result Adjustment

The game result provides a secondary signal that adjusts the CPL-based estimate:

| Result vs Stockfish-1320 | Adjustment |
|--------------------------|------------|
| Win                      | +50 Elo    |
| Draw                     | 0          |
| Loss                     | -50 Elo    |

This accounts for the fact that two players with similar CPL can have different outcomes — the one who wins likely played slightly better in critical moments that raw CPL averaging might miss.

## Step 4: Clamping

The final estimate is clamped to the range **200 – 3000** to prevent absurd outliers from short or anomalous games.

### Anchor Calibration (when using non-1320 benchmark Elo)

The interpolation table is calibrated to a **1320** benchmark anchor. If you configure a different benchmark opponent Elo (`BENCHMARK_STOCKFISH_ELO`), ChessBench applies a linear anchor shift:

`final_elo += (configured_benchmark_elo - 1320)`

Example: if benchmark Elo is set to 1500, all estimates are shifted by +180.

## Step 5: Per-Color and Combined Elo

The system stores three Elo values per player:

- **Elo (White)** — estimated from the game where the LLM played white
- **Elo (Black)** — estimated from the game where the LLM played black
- **Elo (Combined)** — average of white and black Elo, once both games are complete

Per-color Elo is useful because LLMs can have significant asymmetry — some handle the initiative of white better, while others defend more accurately as black.

If only one game has completed so far, the combined Elo equals that single result until the other finishes.

At benchmark start, per-color/combined benchmark Elo fields are reset for participating LLM players so each run is self-contained and does not mix with stale values from prior runs.

## Worked Example

Suppose Claude plays two benchmark games against Stockfish-1320:

**Game 1: Claude (White) vs Stockfish-1320 (Black)**
- Claude's moves: 35 total, 28 survive the eval filter
- Filtered average CPL: 42
- Result: Claude wins (1-0)
- Interpolation: CPL 42 is between 50→1500 and 30→1800. Fraction: (50-42)/(50-30) = 0.4. Elo = 1500 + 0.4 × 300 = **1620**
- Result adjustment: +50 (win)
- **Elo (White) = 1670**

**Game 2: Stockfish-1320 (White) vs Claude (Black)**
- Claude's moves: 40 total, 32 survive the eval filter
- Filtered average CPL: 58
- Result: Claude loses (1-0)
- Interpolation: CPL 58 is between 80→1200 and 50→1500. Fraction: (80-58)/(80-50) = 0.733. Elo = 1200 + 0.733 × 300 = **1420**
- Result adjustment: -50 (loss)
- **Elo (Black) = 1370**

**Combined Elo = (1670 + 1370) / 2 = 1520**

## Why CPL Over Win/Loss?

With only 2 games, traditional Elo from win/loss is extremely noisy. A single blunder can flip a game outcome, and the small sample means confidence intervals would span hundreds of points.

CPL averages over every move in the game (typically 30-50+ per side), giving a much more stable signal. A player who loses but plays 40 accurate moves and one blunder is clearly stronger than one who wins by luck after 40 poor moves — CPL captures this distinction, win/loss does not.

## Stockfish Filtering from Standings

Since Stockfish-1320 is the benchmark tool (not a participant), it is automatically filtered from all standings displays. Only LLM players appear in the scoreboard and rankings.
