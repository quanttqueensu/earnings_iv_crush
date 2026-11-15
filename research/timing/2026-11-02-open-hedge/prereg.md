# Pre-registration: hedge the event straddle at the reaction-session open, or wait for the close

Frozen before any open price is joined to any event. Record:
`outputs/research/prereg_2026-11-02-open-hedge.json`. Scorer:
`research/timing/2026-11-02-open-hedge/study.py`.

## Question

The hedged event hold (`research/timing/2026-11-02-hedged-event-hold/`) starts its stock hedge at the
reaction session's 15:59 close, so the short straddle carries the post-gap delta (near +-0.8 per
share after a large move) through the reaction session. Starting the hedge at that session's open
removes the open-to-close exposure. Which is better is a question about the sign of open-to-close
returns after an announcement gap: continuation (post-announcement drift starting at once) favours the
open hedge; intraday reversal of the overnight reaction favours waiting, because the unhedged short
straddle is positioned against the gap.

## Evidence on each side (to be checked, not assumed)

Intraday trading leans against overnight earnings news in China (overnight-intraday disparity
studies) and US evidence finds the overnight premium after extreme misses disappears intraday
(Liu, Hope and Hu, Journal of Corporate Finance 2023); Berkman, Koch, Tuttle and Zhang (JFQA 2012)
find attention-driven buying at the open reverses during the day. Against that, Bernard and Thomas
(1989) drift and the closed hold study's diagnosis (continuation hurts the in-the-money short leg).
The test is therefore two-sided and the record of either answer sets the hedge timing.

## Data and blocks

- Events: every event scored `ok` in the frozen hedged-hold builds:
  `outputs/research/2026-11-02-hedged-event-hold/events.parquet` (broad, 2013-24) and
  `events_confirm_2025_26.parquet` (broad, 2025-26).
- Open price: Yahoo Finance daily bars (free). As-traded open = the arm's as-traded reaction close x
  (Yahoo Open / Yahoo Close on that same session), so Yahoo's split and dividend adjustments cancel.
  A session with no Yahoo bar, or an Open/Close ratio outside [0.5, 2.0], drops the event (counted).
  Names absent from Yahoo (acquired) drop (counted, compared with kept on the hedged-hold H).
- Blocks: 2013-18, 2019-24 (by entry date), and 2025-26.

## Specification

Arm HO equals arm H of the hedged hold (its stored per-event value) plus an opening hedge held from
the reaction-session open to its close:

`HO = H + [d_o (C - O) - 5e-4 |d_o| O - 3e-4 |d_o| C] / m0`

with `O` the as-traded open, `C` the as-traded reaction close (`settle` when the expiry is the
reaction session, else the first hedging close; both stored in the build as `settle` or derivable as
below), `d_o` the long-straddle Black-Scholes delta at `O`, the strike, years to expiry from the
reaction session (ACT/365) and the diffusive volatility known at entry (`sqrt(jsplit_sd2)` when
`jsplit_valid`, else `s1_iv`, else `front_iv`). The hedge holds `+d_o` shares against the short
straddle. Costs: 5 bp at the open (auction), 3 bp at the close, charged as a round trip with no
netting against the close hedge (conservative).

`C` is reconstructed exactly as the build used it: CRSP as-traded close on the reaction session for
2013-24, Yahoo as-traded close for 2025-26.

## Statistics

- **P1:** paired mean `HO - H` per event, unit `m0`, date-clustered 95% interval (5,000 draws,
  seed 0, clusters on the reaction session), per block.
- **P2:** per-trade Sharpe of HO minus per-trade Sharpe of H, with a date-clustered interval on the
  difference, per block.

## Decision rule

- OPEN HEDGE if P1 > 0 with the interval excluding zero in 2013-18 and 2019-24, and the 2025-26 point
  estimate is > 0.
- WAIT FOR THE CLOSE if P1 < 0 with the interval excluding zero in 2013-18 and 2019-24, and the
  2025-26 point estimate is < 0 (intraday reversal is worth more than the risk reduction).
- Otherwise NO TIMING EFFECT, and P2 decides only if its interval excludes zero in both blocks of
  2013-24 (a pure risk-reduction case).

## Secondary, descriptive

By gap size (|O / previous close - 1| terciles, breakpoints from 2013-18 only), by gap sign, and by
before-open versus after-close reporters.

## Trial accounting

One trial: 1,552 + 1 = 1,553.
