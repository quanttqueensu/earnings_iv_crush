# Pre-registration: stacked execution levers under the G1 gate on the hedged event hold

Frozen before the combined outcome is computed for any block. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-09-combined-levers-hedged-hold.json`. Scorer:
`research/selection/2026-11-09-combined-levers-hedged-hold/study.py`.

## Hypothesis

Selling the front at-the-money straddle at 15:59 before an announcement, choosing the cheaper leg
by put-call parity at entry, replacing the buy-back with a stock hedge held to expiry (arm H), and
trading only events that pass the G1 gate (high term spread and a tight entry spread) earns a
positive net return per trade on margin, and the gate selects better than random events of the
same tenor. Mechanism: each lever removed one measured cost on its own (the exit crossing, the
dearer entry leg), and the gate keeps events whose front premium is rich relative to the back
month while the entry crossing is cheap. No earlier study combined them.

## Closest prior work and closed studies

Dubinsky, Johannes, Kaeck and Seeger (RFS 2019) on the priced earnings jump; Goyal and Saretto
(JFE 2009) on option returns and the volatility gap. Closed rows: the hedged event hold
(2026-11-02, exit lever confirmed, book not confirmed: 2025-26 mean H -0.10% of margin
[-0.89%, +0.66%], N=1,597), the parity leg choice (lever, book fail), the term gate q=0.80
(fails forward on the buy-back), and the 2026-11-07 pairwise tercile gates (term by spread passes
on residual value but the lift is largely tenor composition). This study differs by scoring the
stacked book, not each lever, and by stratifying on tenor.

## Data and blocks

- Events: arm H `ok` events from `outputs/research/2026-11-02-hedged-event-hold/events.parquet`
  (2013-24) and `events_confirm_2025_26.parquet` (2025-26), joined on ticker and entry date to
  the non-megacap events of `outputs/research/ml_zoo/events_full.parquet` (features, announcement
  date). Inner join; the funnel is printed.
- Parity lever: `adv_pos` from
  `outputs/research/2026-11-02-parity-leg-choice/events_amend01.parquet` (the no-look-ahead
  amendment), already in units of `m0`. Events whose `status_p` is not `ok` (a dividend before
  expiry) and events absent from that file take `adv_pos = 0`: the lever is simply not used, which
  is the executable choice, not an imputed gain.
- Blocks by announcement year: discovery 2013-2018, validation 2019-2024, confirmation 2025-2026.
- Disclosed prior views. H, and the parity add-on, have been viewed by block in aggregate. On
  2026-11-07 the term-spread top tercile crossed with the half-spread bottom tercile was viewed on
  H in 2025-26 (mean +1.78% of margin, N=317) and on the buy-back by block and tenor in all three
  blocks. G1's cuts (two-thirds quantile and median) differ from those terciles but overlap them
  heavily. No block is untouched for this combination: a pass here is weak evidence, and the
  forward paper book under the forward-gates pre-registration is the real test.

## Specification

- Outcome per event: `C = H + adv_pos`, net, on margin `m0`, as frozen in the two source studies.
- Features at 15:59 on the entry date: `iv_term_spread` from the zoo file, and the entry
  half-spread `(mid0 - s0) / mid0` from the hedged-hold file. These are the historical forms of
  the live `iv_term_spread_nearest` and `entry_rel_spread`; the relative spread is twice the
  half-spread, so the median cut is the same.
- G1: `iv_term_spread` at or above its causal two-thirds quantile and the half-spread at or below
  its causal median. Each quantile uses finite values from events with strictly earlier
  announcement dates, over the full sequence 2013-2026, and is undefined (event not scored) with
  fewer than 200 such values.
- Tenor bucket: calendar days from the exit date to the expiry, 0-1, 2-4, 5-9, 10 or more.
- Excluded levers: maker entry (measured only on 2025-26 and its book statistic was not readable
  for ledger attrition) and the smile strangle (a different structure, not confirmed on 2025-26).

## Primary statistics and inference

- P1, the book: per-trade Sharpe of C over G1-selected events per block, and the mean of C, with
  date-clustered 95% intervals (announcement dates resampled, 5,000 draws, seed 0).
- P2, the gate: the tenor-matched random null, drawing in each tenor bucket as many scored events
  as G1 selected there (5,000 draws, seed 0), on the mean of C; the percentile of G1's observed
  mean. Also the within-tenor difference, selected minus unselected mean C, weighted by the
  selected count over buckets with at least two of each, with a date-clustered interval.
- Secondary, reported and never read for the verdict: C without the gate, H under the gate, and
  the funnel.

## Success criterion

PASS only if all hold: P1 Sharpe interval excludes zero from above in validation and in
confirmation, the P1 discovery point is above zero, and the P2 null percentile is at least 95 in
discovery and in validation. A pass is reported as "conditional on blocks partly seen" and goes to
the forward paper book, never straight to the live rule.

## Kill criterion

Anything else is FAIL. A P1 interval wholly below zero is reported as such. A gate that beats the
tenor-matched null while the book's interval spans zero is reported as "selection without a
book" and does not count as a pass.

## Trial accounting

One trial. The largest count in the hash records is 1,591
(`prereg_2026-11-07-analyst-disagreement-hedged-hold.json`), so this is trial 1,592.
