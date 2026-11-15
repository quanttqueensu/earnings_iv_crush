# Pre-registration: ex-diffusive implied jump against a causal jump forecast

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record: `outputs/research/prereg_2026-10-20-jump-richness.json`.
Scorer: `research/selection/2026-10-20-jump-richness/study.py`.

## Hypothesis

Events whose implied announcement jump, isolated from diffusive volatility by the two-expiry
split, is large relative to the name's own causal history of announcement moves carry more
residual value at exit on the next-session short straddle. Mechanism: the jump the market charges
for is the object being sold; total implied move mixes in diffusive volatility, which varies by
tenor and regime and may have masked the signal in the closed own-history test.

Nearest closed work: own-history richness on clean IV (`selection/findings/clean_iv.md`), which
used the total implied move; the 375-strategy zoo, whose features included implied over
historical move but not the ex-diffusive jump. Closest published: Dubinsky, Johannes, Kaeck and
Seeger (RFS 2019).

## Data and blocks

Events `outputs/research/ml_zoo/events_full.parquet`; chains `data/cache/backfill_chains/` at the
entry and exit 15:59 ET; CRSP `dsf` for the exit close; announcement history from
`outputs/research/panel_events.parquet` (IBES dates since 1996, linked by permno). Discovery
2013-2018, validation 2019-2024 (entry dates). Confirmation 2025-26 is not run: the 2025-26
next-session outcomes have been viewed for several selectors.

## Specification

- Book: the shortest expiry on or after the exit date (E1), strike nearest the parity forward with
  both legs two-sided, sold at the entry 15:59, bought back at the exit 15:59 on the same contract
  (`chains._mark`). Margin 0.20 F + entry straddle mid.
- Jump split: E2 = the next expiry at least 7 days after E1. sd2 = (V2 - V1) / (T2 - T1),
  J = V1 - sd2 T1, valid if sd2 > 0 and J >= 0. Implied jump vol sJ = sqrt(J).
- Jump forecast: for each prior announcement of the name (strictly before the entry date), the
  two-day market-adjusted return over [day0, day0+1] from CRSP `ret`, net of the Fama-French
  market return (mktrf + rf from `panel_daily`). Jhat^2 = (r_last^2 + mean of last 4 r^2 + mean of last 8 r^2) / 3, with at least 4
  prior announcements.
- Signal: sJ / Jhat. Terciles from all events with strictly earlier entry dates, minimum 200.
- Outcome (protocol P4): R_adj = -(exit mark - BS straddle at the exit close, strike, exit time to
  expiry and the event's back-month ATM IV from the events table) / margin, the definition used by
  the section 2.1 study. Secondary: net RoM at the measured cost (1.2714% of the entry mid, 3.0182%
  of the exit mid).

## Primary statistic and inference

Top-minus-bottom tercile mean R_adj, cluster bootstrap on entry dates, 5,000 draws, seed 0. The
top tercile's mean net RoM against `protocol.matched_random_null` over all tercile-assigned
events in the block.

## Success criterion

Top-minus-bottom lower bound above zero in discovery and in validation, and the top tercile at or
above the 95th percentile of the matched null in both.

## Kill criterion

Discovery lower bound at or below zero closes the idea; validation is then not run.

## Trial accounting

One trial. Count after this date's seven declared trials: 1,539.
