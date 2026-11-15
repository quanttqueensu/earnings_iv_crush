# Amendment 01: a 2025-26 confirmation block for the hedged event hold

Frozen before any 2025-26 outcome of this trade is computed. Amends `prereg.md` (SHA-256
3e80d470da881715b7cecd1939a2573c3257f64b4f83ca790492c1e7fc1e6332) without editing it. Record:
`outputs/research/prereg_2026-11-02-hedged-event-hold-amendment-01.json`. Scorer:
`research/timing/2026-11-02-hedged-event-hold/confirm.py`.

## Why

The frozen study excluded 1,690 events (entries 2025-01-14 to 2026-08-06, 335 names) only because
CRSP on disk ends on 2024-12-31. The discovery and validation results are known (exit lever passes in
both; the standalone book fails). An untouched third period tests whether the exit lever carries
forward. The data needed is free.

## Change of stock source, and nothing else

- Stock path: Yahoo Finance daily bars (`yfinance`, `auto_adjust=False`), free. The as-traded close
  on date d is `Close_d` multiplied by the product of split ratios with ex-date after d; the
  close-to-close total return is the ratio of `Adj Close`. A split between the reaction session and
  expiry drops the event (counted), as in the frozen study.
- Equity half-spread: fixed at 3 bp per side for every hedge trade (the 90th percentile of CRSP
  closing half-spreads across the study's names in 2024 is 2.93 bp; median 1.0 bp), floored at
  1 bp as before. This is conservative relative to the CRSP-based blocks.
- Any session from the reaction session to the settlement session missing from the Yahoo bars drops
  the event (counted). Events whose settlement session is after the last Yahoo bar are dropped
  (counted).
- Everything else (contract, sale at the entry bids, arms B and H, hedge volatility, settlement,
  commissions, margin unit `m0`, statistics) is exactly the frozen specification.

## Data-path check, before the confirmation is read

The Yahoo path is run on the 2024 events, which CRSP also covers, and compared with the CRSP-based
H per event. If the mean absolute difference in H exceeds 0.25% of `m0`, or the correlation is
below 0.98, the confirmation is reported as "data path not validated" and its verdict is not read.

## Confirmation criterion

Block 2025-01 to 2026-10 by entry date. The exit lever is CONFIRMED if the mean `H - B` is
positive with its date-clustered 95% interval excluding zero. The standalone book (per-trade Sharpe
of H with its interval) is reported, and the book is CONFIRMED only if that interval also excludes
zero from above. No other statistic can confirm.

## Trial accounting

One further trial (a confirmation of an existing family on a new block): 1,550 + 1 = 1,551.
