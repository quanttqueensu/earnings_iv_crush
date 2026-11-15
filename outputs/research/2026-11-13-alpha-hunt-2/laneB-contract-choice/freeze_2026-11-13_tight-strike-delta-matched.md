# Freeze: tightest-quoted adjacent strike, delta-matched over the event night (trial 1,819)

Frozen 2026-11-13, before any 2019-24 outcome of an alternative strike was computed. Read once.

## Provenance

The rule (pick the narrowest straddle quote among the ATM strike and its two listed neighbours)
was stated before scoring (1812). The entry-night delta match is a fix of the 1811/1812 failure
diagnosis (strike-step directional noise), stated before 1819 was scored. No reversal of a failed
direction. The held-out block 2019-24 has not been read for any alternative-strike outcome
(blocks.csv and trials 1,555, 1,557, 1,560 checked), so it is clean for this outcome and feature
family; the level of H itself has been viewed in every block.

## Specification

- Events: `ok` events of the hedged event hold, entry years 2019-24, with the ATM strike and at
  least one listed neighbour two-sided at 15:59 (`arms.parquet`).
- Choice: among K-1, K0, K+1 (adjacent listed strikes with both legs two-sided on the front
  expiry), the strike whose straddle has the smallest dollar quoted spread (ask - bid, both
  legs) at the last 15:59 ET record; K0 wins ties.
- The chosen straddle is sold at its 15:59 bids and hedge-held by the frozen `build_event`.
  When the choice is not K0, (delta_alt - delta_K0) shares are held from the entry close to the
  reaction close (CRSP), paying the CRSP closing half-spread (floored at 1 bp) on both trades.
  Deltas: Black-Scholes straddle delta on the entry parity forward at each strike's 15:59 mid IV.
- Outcome per event: (chosen P&L - H P&L) / m0, net at the touch, per trade; zero when K0 is kept.

## Statistics and criterion

- Primary: mean gain over all eligible events, `date_clustered_ci` (reaction-date clusters,
  5,000 draws, seed 0); t as in the lane log.
- Null: the same number of events switched to a random available neighbour (each with its own
  delta match); percentile of the observed mean.
- CONFIRMED STRIKE LEVER if the interval excludes zero above, t >= 3 and null percentile >= 95.
  Otherwise not confirmed. The level of the chosen book is reported beside it.

## Discovery reading (2013-18, already seen)

+0.10% of m0 [+0.01, +0.19], t 2.2, null percentile 100, N 2,550; level -0.83% of m0.
Expected power is low: a held-out t of 3 needs a larger effect than discovery showed.

## Code and data at freeze (sha256, first 12)

6497658c7740  score.py
32f9ffdd4395  build.py
89f7718a562e  wings.py
29aa1a4ee12e  arms.parquet
772dfef1c2ed  wings.parquet

Freeze time: 2026-11-13T18:11:18Z
