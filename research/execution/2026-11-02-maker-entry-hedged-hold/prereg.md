# Pre-registration: resting entry plus hedged hold, a book that crosses no option spread by design

Frozen before the policy's fills are computed. Record:
`outputs/research/prereg_2026-11-02-maker-entry-hedged-hold.json`. Scorer:
`research/execution/2026-11-02-maker-entry-hedged-hold/study.py`.

## Hypothesis

Two closed results combine into a trade that has not been scored. The resting-order study (F1,
`research/execution/findings/flow_liquidity.md`) failed only its 5-minute markout gate; the hedged
event hold removes the exit crossing (exit lever confirmed in three blocks). Under a policy that
always trades (rest each leg at the 15:00 mid; at 15:59:00 cancel what has not filled and sell at
the bid) the event outcome is identical to the crossing entry, so the paired difference is exactly
the sum over filled legs of (limit minus the 15:59:00 bid). The markout is inside that number, not
a separate gate. Combined with the hedged hold, the option position crosses no spread unless a leg
fails to fill. Hypothesis: the paired entry improvement is positive, and the combined book (HM) has a
positive per-trade Sharpe.

## Prior exposure of this block (disclosed)

F1 measured resting entry fills on the 2025-26 broad block against a 15:59:59 cross (entry-only
+1.38% of margin) and found 5-minute markouts of -0.68 of the half-spread. The 15:59:00 cancel rule,
the paired difference against the 15:59:00 bid, and every outcome of the combined book are new. The
block is therefore not untouched for the fill component, and a pass is recorded as "conditional on
a block partly seen", to be confirmed on the paper book's own fills.

## Data

- Events: the 2025-26 broad ledger (`outputs/research/oos_2026_ledger.csv`) joined with the 2025-26
  confirmation build of the hedged hold on ticker and entry date (1,136 events), traded in the
  ledger's own contract (strike, expiry), whose ticks are on disk in
  `data/cache/flow/broad_2025_2026/{T}_{entry}_pre.parquet`.
- Fills: F1's own functions (`research/execution/research_flow_liquidity.py`): limit is the 15:00
  mid rounded down to a legal penny-schedule tick; strict fill rule (a print through the limit or a
  bid at or above it); window 15:00:00 to 15:59:00.
- Sale price of the crossing arm and of unfilled legs: the last two-sided bid at or before 15:59:00.
- Arm H on the ledger contract: `hedged_short_straddle` exactly as frozen in the hedged-hold study,
  sale at the 15:59:00 tick bids, mid credit at the 15:59:00 tick mids, forward and hedge volatility
  as frozen, exit quotes from the reaction-session chain, Yahoo stock path and 3 bp equity cost as in
  amendment 01. Arm HM = H + sum over filled legs of (limit - 15:59:00 bid) / m0.
- Exclusions (counted): no tick file, a leg with no two-sided quote at 15:00 or 15:59:00, an early
  close, any hedged-hold exclusion.

## Statistics and criterion

- P1: mean HM - H per trade, unit m0, date-clustered 95% interval. Pass if > 0 with the interval
  excluding zero.
- P2: per-trade Sharpe of HM with its interval. Pass if the interval excludes zero from above.
- Attrition guard: the ledger drops events whose exit leg had no bid (large moves). Mean H on the
  joined set is compared with mean H on all 1,597 confirmation events; if it is higher by more than
  0.5% of m0, P2 is reported as "biased by ledger attrition, not read" and an imputed book (all-event
  H plus the joined mean improvement) is reported instead, labelled as an estimate.
- Secondary: both-leg fill rate, per-leg markout to 15:59:00, improvement by implied-move tercile.

## Trial accounting

One trial: 1,553 + 1 = 1,554.
