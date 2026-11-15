# Pre-registration: sell a later expiry for the hedged event hold

Frozen before any later-expiry outcome is computed. Record:
`outputs/research/prereg_2026-11-02-later-expiry-hedged-hold.json`. Scorer:
`research/timing/2026-11-02-later-expiry-hedged-hold/study.py`.

## Hypothesis

With no exit crossing (the hedged event hold), the cost of holding longer is only stock-hedge
cost, while options keep losing value for about two weeks after high-expected-volatility
announcements (de Silva, So and Smith, Review of Finance 2025). Selling the expiry at least seven
calendar days after the front, and hedge-holding it to its own expiry, collects that post-event decay
on top of the event crush, with a single option crossing. Against it: the later straddle carries a
smaller share of event variance per dollar of premium (Dubinsky et al. 2019 term structure), and its
entry spread in dollars is larger. The paired test decides.

## Data and blocks

- Events: every event scored `ok` in the frozen hedged-hold builds (2013-24 CRSP; 2025-26 Yahoo,
  amendment 01). Arm H is the stored per-event result on the front contract.
- Arm L: expiry = the first listed expiry at least 7 calendar days after the front expiry, in the
  entry 15:59 chain (`data/cache/backfill_chains/{T}_{entry}.parquet`); strike and touch by
  `hedged_hold.atm_quote` on that expiry (parity forward, nearest two-sided strike); sale at the sum
  of the two bids. Hedged hold exactly as frozen (hedge from the reaction-session close, volatility
  from the reaction-session chain mid at that strike and expiry, else `s2_iv`; settle at intrinsic
  on the expiry close; CRSP or Yahoo stock as in the arm-H build; equity cost as in that build).
  Exclusions counted: no later expiry within 60 days, no two-sided ATM pair, settlement after the
  stock data, split in the hold, missing closes.
- Blocks by entry date: 2013-18, 2019-24, 2025-26.

## Statistics

Common unit per event: `mc = 0.20 x front forward + max(front sale, later sale)`. Both arms'
per-share net P&L are divided by `mc`.

- P1: mean `L - H` per trade, unit `mc`, date-clustered 95% interval, per block.
- P2: per-trade Sharpe of L minus that of H, interval by resampling dates (paired), per block.

## Decision rule

LATER EXPIRY if P1 > 0 with the interval excluding zero in 2013-18 and 2019-24 and the 2025-26
point estimate > 0, and P2's point estimate is >= 0 in both 2013-24 blocks. FRONT EXPIRY if P1 < 0
with the interval excluding zero in both 2013-24 blocks. Otherwise NO DIFFERENCE.

## Secondary, descriptive

Decomposition of L - H into entry half-spread, event-window P&L and post-reaction P&L; by implied-
move tercile; the hedge's peak notional.

## Trial accounting

One trial: 1,554 + 1 = 1,555.
