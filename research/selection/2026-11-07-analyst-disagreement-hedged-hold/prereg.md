# Pre-registration: analyst disagreement as a selector for the hedged event hold

Frozen before the disagreement feature is joined to any outcome. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-07-analyst-disagreement-hedged-hold.json`. Scorer:
`research/selection/2026-11-07-analyst-disagreement-hedged-hold/study.py`. Generated as Spec C of
`_private/reports/alpha_pivot_slate_2026-11-07.md`, with four corrections listed at the end.

## Hypothesis

Within an implied-move tercile and a tenor bucket, events whose analysts disagree most earn more
from the hedged hold per unit of premium than the other events in that cell. Mechanism: retail
option demand concentrates on salient uncertainty before announcements (de Silva, So and Smith,
RoF 2025), bidding up the straddle, while forecast dispersion partly reflects differences in
analysts' models rather than information the release resolves. Closest prior work: Wang (RAF 2020)
on dispersion and option-implied risk; the nearest closed rows are the IVOL and MAX selectors of
2026-11-02, which used the same base trade, decile and burn-in.

## Data and blocks

- Base trade and outcome: arm H of the hedged event hold, status `ok`, from
  `outputs/research/2026-11-02-hedged-event-hold/events.parquet` (2013-24) and
  `events_confirm_2025_26.parquet` (2025-26). Announcement dates from
  `outputs/research/2026-10-20-hedged-hold/features.parquet`.
- Disagreement: `data/processed/wrds/raw/tr_ibes.statsum_epsus.*.parquet` (EPS, quarterly), linked
  to CRSP `permno` through `wrdsapps_link_crsp_ibes.ibcrsphist`. Event permnos come from the
  features file; 2025-26 events, which carry none, take their ticker's latest 2013-24 permno.
- Blocks by announcement year: discovery 2013-2018, validation 2019-2024, confirmation 2025 to
  2026-01-15 (the last IBES `statpers`). Disclosed: H has been viewed by block in aggregate and for
  IVOL and MAX deciles; it has never been split by any IBES feature.

## Specification

- Feature `D = stdev / F0`, with `stdev` from the IBES row whose `statpers` is the latest strictly
  before the entry date and at most 40 calendar days before it (IBES summaries are monthly), whose
  `fpedats` is the latest fiscal period end strictly before the announcement date, and whose
  `numest` is at least 3. Where the link table maps several IBES tickers to the permno on the
  date, the one with the lowest `score` is used. `F0 = (m0 - s0) / 0.20` is the entry forward.
  The IBES `actual` and `anndats_act` fields are never read.
- Implied move `IM = mid0 / F0`. Implied-move terciles from
  `earnings_iv_crush.research.hedged_hold.causal_bins` (3 bins, 200 prior events, strictly
  earlier announcement dates over the full sequence).
- Treated: top decile of D within the event's implied-move tercile, deciles from `causal_bins`
  (10 bins, 200 prior events) run separately within each tercile.
- Tenor bucket: calendar days from the exit date to the front expiry, 0-1, 2-4, 5-9, 10 or more.
- Outcome: H per unit of premium, `H x m0 / mid0`, net on the frozen basis.
- Funnel at every step: events, permno, IBES row found, D finite, tercile assigned, decile
  assigned.

## Primary statistic and inference

- Delta: over cells of implied-move tercile by tenor bucket with at least two treated and two
  untreated events, the treated-count-weighted mean of (treated mean minus untreated mean) of the
  outcome; date-clustered bootstrap interval (announcement dates resampled, 5,000 draws, seed 0).
- Null: per-trade Sharpe of H on m0 for the treated events against random draws that match the
  treated count within each cell (5,000 draws, seed 0); the percentile of the observed value.

## Success criterion

Discovery: Delta's lower bound above zero and the null percentile at least 95. If discovery passes,
validation on the same two conditions. If both pass, confirmation reports Delta and the treated
mean H with intervals (underpowered, stated in advance); a pass needs both point estimates above
zero.

## Kill criterion

A discovery miss on either condition closes the idea; validation and confirmation are not scored.
A Delta interval wholly below zero is reported as such and never reread as a buyer's trade.

## Trial accounting

One trial. The largest count in the hash records is 1,590
(`prereg_2026-11-07-pairwise-tercile-gates.json`), so this is trial 1,591.

## Corrections to the slate's draft

1. The draft's implied move `mid0 / s0` is a spread ratio; the implied move is `mid0 / F0`.
2. Tenor buckets are added to the strata, because outcomes on this book vary with days to expiry
   (`outputs/research/2026-11-07-pairwise-tercile-gates/tenor_diagnostic.log`).
3. Price scaling uses the entry forward on disk for every block rather than CRSP, which ends in
   2024.
4. Trial numbering follows the hash records (1,591), not the draft's 1,572.
