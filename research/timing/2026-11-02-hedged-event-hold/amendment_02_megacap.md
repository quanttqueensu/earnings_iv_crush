# Amendment 02: the megacap universe for the hedged event hold

Frozen before any megacap outcome of this trade is computed. Amends `prereg.md` (SHA-256
3e80d470...) without editing it. Record:
`outputs/research/prereg_2026-11-02-hedged-event-hold-amendment-02.json`. Scorer:
`research/timing/2026-11-02-hedged-event-hold/megacap.py`.

## Why

The frozen population was every event in `events_full.parquet`, but the 1,794 megacap events
(block `megacap`, 50 names, 2013-04 to 2024-12) have no front quote in the features file, so the
frozen run scored the broad universe only. Their 15:59 quote strips at entry and exit are on disk in
`data/processed/databento_quotes/{TICKER}/{DATE}_chain.parquet` (consolidated BBO, the megacap
book's marking basis). No spend.

## Change of quote source, and nothing else

- Front contract at entry, by the frozen rule: the first expiry on or after the reaction session;
  within it the parity forward from the strike with the smallest |call mid - put mid| among strikes
  with both legs two-sided, then the two-sided strike nearest that forward; sale at the sum of the
  two bids. Built with `hedged_hold.atm_quote` on the entry strip.
- Exit quotes for the same strike and expiry from the reaction-session strip; a leg absent from the
  strip drops the event (counted); a zero bid with a positive ask is kept (B defined, no exit mid).
- Hedge volatility from the exit strip mid as frozen, else `s2_iv` from the features file if present,
  else the event drops (counted).
- Stock: CRSP as frozen (permno from the features file); events with no permno drop (counted).
- Everything else is the frozen specification. Blocks: 2013-18 and 2019-24 by entry date.

## Criterion

Reported as a universe extension of the same trial family. The exit lever holds in megacap if the
mean `H - B` is positive with the interval excluding zero in both blocks; the standalone book is
read as in the frozen text (validation Sharpe interval above zero and discovery point above zero).

## Trial accounting

One further trial: 1,551 + 1 = 1,552.
