# Pre-registration: pre-announced releases on the megacap ledger, a replication

Frozen before any outcome for the declared block is computed. Record:
`outputs/research/prereg_2026-11-10-preannounced-megacap-replication.json`.
Scorer: `research/selection/2026-11-10-preannounced-megacap-replication/study.py`.

## Hypothesis

The pre-announced-release effect read on the broad ledger (trial 1,604: Delta +0.066
[+0.003, +0.130], failed its null-percentile condition) also appears on the megacap ledger, whose
50 names and events are disjoint from the broad ledger.

## Data and blocks

Megacap arm of the hedged event hold, `outputs/research/2026-11-02-hedged-event-hold/
events_megacap.parquet`, status `ok` (1,183 of 1,794; the 398 events without an exit leg at the
strike are the ledger's known attrition and are reported, not repaired). Announcement dates from
`outputs/research/ml_zoo/events_full.parquet`; permno from the hedged-hold features file, else the
characteristics panel's ticker map. Filing flag from the hackathon 8-K panel exactly as trial
1,604. One block: announcement dates 2015-04-01 to 2024-12-31. Counted before freezing, from
filing metadata only: 906 covered events, 53 treated, 23 of them TSLA. No megacap outcome has been
split by this flag.

## Specification

Flag, coverage rule, cells (causal implied-move tercile within this ledger, 200-event burn-in,
crossed with tenor bucket), outcome `y = H x m0 / mid0` and Delta as in
`research/selection/2026-11-10-hackathon-panels/prereg.md` trial P1.

## Primary statistic and inference

Delta with a date-clustered interval (5,000 draws, seed 0) and the cell-matched null percentile.
Secondary, unable to rescue: the same excluding TSLA.

## Success criterion

Delta interval lower bound above zero and null percentile at least 95.

## Kill criterion

Anything else is "not replicated". With 53 treated events the test has little power (the interval
half-width is expected near 0.15 against an effect of 0.07), so a miss with a positive point
estimate leaves the broad reading where it was and a negative point estimate weakens it. Stated
now so neither is reread later.

## Trial accounting

One trial, number 1,608.
