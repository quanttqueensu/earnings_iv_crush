# Amendment 01: 2025-26 confirmation of the smile-strike structure lever

Frozen before any 2025-26 strangle outcome is computed. Amends `prereg.md` (SHA-256
30a14c2a70d0e3e8f0dec7619ce9eb1d90a8df5d7115b868080db7545d3d8e1b) without editing it. Record:
`outputs/research/prereg_2026-11-02-smile-strike-hedged-hold-amendment-01.json`. Scorer:
`research/execution/2026-11-02-smile-strike-hedged-hold/confirm.py`.

## Why

The frozen study returned BOOK FAIL and STRUCTURE LEVER: on the same events the hedged
one-implied-move strangle has a higher per-trade Sharpe than the hedged ATM straddle in both 2013-18
and 2019-24, while its own Sharpe is negative in both. The prereg states that a pass is confirmed on
2025-26 before any claim.

## Data and specification

Events: every `ok` event of the hedged event hold's 2025-26 confirmation
(`outputs/research/2026-11-02-hedged-event-hold/events_confirm_2025_26.parquet`, arm H as frozen).
Stock path: Yahoo Finance through `confirm.yahoo_paths` of the hedged event hold (as-traded close,
Adj Close returns, 3 bp fixed equity half-spread), the same source arm H used on this block.
Everything else is the frozen specification, unchanged.

## Criterion

- CONFIRMED if the paired `Sharpe(G) - Sharpe(H)` interval on 2025-26 excludes zero above.
- The book reading (G's own per-trade Sharpe and its interval) is reported; it cannot be rescued
  by this block, which was not part of the book criterion.
- Attrition guard as frozen (0.5% of m0).

## Trial accounting

A confirmation of an already-counted trial; no new trial. Count stays 1,557.
