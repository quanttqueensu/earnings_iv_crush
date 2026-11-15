# Freeze: vol-tight half-implied-move strangle under the hedged hold (trial 1,826)

Frozen 2026-11-13, before any 2019-24 outcome of this construction was computed. Read once.

## Provenance

Discovery-derived. The structure (strangle under the hedged hold) was proposed before scoring
(1815), but the wing width (IM/2 rather than the 1-IM of trial 1,557), the wing rule (1821) and the
vega-matched statistic (1822) were chosen after reading discovery results. The held-out block is
not clean for this outcome family: trial 1,557 scored the 1-IM strangle's Sharpe against H on
2019-24. Whatever the read, the label is exploratory.

## Specification

- Events: `ok` events of the hedged event hold, entry years 2019-24, with both IM/2 wings and a
  built strangle (`wings.parquet`, `arms.parquet`).
- Wings: start from the frozen smile-study rule at half the implied move (smallest listed call
  strike at or above fwd x (1 + IM/2) with a positive bid; largest put strike at or below
  fwd x (1 - IM/2)). Each wing moves to the adjacent listed strike (one step either side, calls
  kept above the forward, puts below) when that strike's 15:59 quote has a strictly smaller
  dollar spread per unit of Black-Scholes vega at its own mid IV. Decision time: last 15:59 ET
  record of the entry chain.
- Sale at the two 15:59 bids; hedged hold, settlement and costs exactly as the frozen `build_g`.
- Size: the strangle is scaled so its entry vega equals the ATM straddle's (H) entry vega.
- Outcome per event: scaled strangle P&L / m0 minus H, net at the touch, per trade.

## Statistics and criterion

- Primary: mean paired difference, `date_clustered_ci` (reaction-date clusters, 5,000 draws,
  seed 0), t = point / ((high - low) / 3.92).
- STRUCTURE LEVER (held-out) if the interval excludes zero above and t >= 3. No selection is
  involved (every covered event is traded), so no matched null applies.
- Level: mean of the scaled strangle per m0 with its interval. A lever that leaves the level
  below zero is cost recovery, not alpha.
- Attrition: mean H of events with no IM/2 wing against covered events, printed.

## Discovery reading (2013-18, already seen)

+0.49% of m0 [+0.28, +0.70], t 4.5, N 2,447; level -0.39% [-0.82, +0.05].

## Code and data at freeze (sha256, first 12)

6497658c7740  score.py
32f9ffdd4395  build.py
89f7718a562e  wings.py
29aa1a4ee12e  arms.parquet
772dfef1c2ed  wings.parquet

Freeze time: 2026-11-13T18:11:18Z
