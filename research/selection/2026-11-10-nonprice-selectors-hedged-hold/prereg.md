# Pre-registration: non-price information selectors on the hedged event hold

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-10-nonprice-selectors-hedged-hold.json`.
Scorer: `research/selection/2026-11-10-nonprice-selectors-hedged-hold/study.py`.

## Hypothesis

Events whose information content is lower for a reason that is not an option or stock price earn
more residual value per unit of premium for the seller, within an implied-move tercile and tenor
bucket, because the implied move is quoted from the name's reaction history and bought by
calendar-driven demand. Five trials:

- **V1, stable 10-K language.** Names whose latest annual report changed its risk-factor text
  least carry fewer surprises (Cohen, Malloy and Nguyen, JF 2020, find that changes predict future
  earnings and news).
- **V2, demand in line.** Names whose consumer-demand score sits near the cross-sectional middle
  carry smaller surprises than names at either extreme.
- **V3, pre-announced releases.** A preliminary-results 8-K (Item 2.02) 3 to 44 days earlier has
  already released the news (Rogers, Skinner and Van Buskirk, JAE 2009).
- **V4, concurrent filers.** Names that habitually file the 10-Q or 10-K with the release show a
  muted reaction (Arif, Marshall, Schroeder and Yohn, JAE 2019).
- **V5, any flag.** An event carrying at least one of the V1, V3 and V4 flags earns more than one
  carrying none.

## Data and blocks

- Outcome: arm H of the hedged event hold, `outputs/research/2026-11-02-hedged-event-hold/
  events.parquet` (status `ok`) and `events_confirm_2025_26.parquet`, net on the frozen basis as a
  fraction of `m0`. Residual value per unit of premium `y = H x m0 / mid0`.
- Announcement date and permno: `outputs/research/2026-10-20-hedged-hold/features.parquet`.
- V1: `data/cache/lazy_prices/similarity_10k.parquet` (34,462 consecutive 10-K pairs, 2014-01 to
  2026-09, built from public filings for another project) and `cik_permno.parquet`.
- V2: `data/cache/carbonarc/ca_demand.parquet` (2017-03 to 2026-10; current vintage, not
  point-in-time, survivors only, one month of lag imposed in the file).
- V3, V4: `data/cache/edgar/submissions/*.json`, the `recent` filing arrays only (no network
  request), ticker to CIK from `data/cache/edgar/company_tickers.json`.
- Blocks by announcement date. V1: discovery 2015-18, validation 2019-24, confirmation 2025-26.
  V2: discovery 2017-20, validation 2021-24, confirmation 2025-26. V3, V4, V5: discovery 2019-21,
  validation 2022-24, confirmation 2025-26, because the cached arrays reach a median earliest
  filing of 2018.
- Outcomes viewed before: H in aggregate by block, by IVOL and MAX deciles, by analyst
  disagreement, and under the pairwise tercile gates and G1. None split by any filing-text,
  Carbon Arc or EDGAR feature. The 10-K similarity was scored against monthly stock returns in the
  other project, never against an option outcome.

## Specification

- **Cells.** Implied move `mid0 / F0`, `F0 = (m0 - s0) / 0.20`, cut into causal terciles
  (`hedged_hold.causal_bins`, 200-event burn-in), crossed with the tenor bucket of the exit-to-expiry
  gap in days (0-1, 2-4, 5-9, 10+). Identical to the analyst-disagreement study.
- **V1.** The latest 10-K pair for the name with `info_date` strictly before the entry date and no
  more than 400 days before it, similarity `10K_1A__sim_cosine`. Its percentile is taken among all
  pairs in the file with `info_date` in the 365 days strictly before the entry date, which is
  causal and absorbs the years in which a rule change moved every filer's text. Treated if the
  percentile is at least 0.80.
- **V2.** `a = |ca_demand|` at the latest `eom` strictly before entry and no more than 62 days
  before it. Causal quintiles of `a`; treated if in the lowest.
- **V3.** Treated if a filing with form `8-K` (not `8-K/A`) lists item `2.02` with acceptance date
  in `[d - 44, d - 3]` calendar days, `d` the announcement date. Window derivation is in
  `_private/reports/alpha_pivot_slate_2026-11-07.md` (filing-gap trough, metadata only). Scored
  only if the name's cached array starts at least 120 days before `d`.
- **V4.** An Item 2.02 8-K is concurrent if a `10-Q` or `10-K` is accepted between 0.5 hours
  before and 1.0 hour after it. Treated if at least 3 of the name's 4 most recent Item 2.02 8-Ks
  accepted at least 45 days before `d` were concurrent; unscored with fewer than 4.
- **V5.** Among events with V1, V3 and V4 all defined, treated if at least one of the three flags
  is set.
- No parameter was swept; each follows the cited derivation or the project's standing rule.

## Primary statistic and inference

Delta: the treated-count-weighted mean over cells of [mean `y`, treated] minus [mean `y`,
untreated], cells needing at least two of each. Date-clustered bootstrap on announcement date,
5,000 draws, seed 0. Beside it, the percentile of the treated per-trade Sharpe of H among 5,000
random selections matched on count within cell, seed 0. Secondary, unable to rescue a failure:
treated mean H and per-trade Sharpe with intervals; attrition funnel per trial.

## Success criterion

Per trial, in order: discovery Delta interval lower bound above zero and null percentile at least
95; then the same two conditions on validation; then confirmation Delta above zero and treated
mean H above zero, reported with intervals.

## Kill criterion

A trial that misses either discovery condition is closed and its later blocks are not scored. A
Delta interval wholly below zero is reported as the opposite sign and is not rescued as a buyer's
trade.

## Trial accounting

Five trials, V1 to V5, numbered 1,598 to 1,602 after the directional study's 1,597. No trial can
rescue another.
