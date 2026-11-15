# Pre-registration: pre-event directional signals on the earnings night, stock vehicle

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-10-pre-event-direction.json`.
Scorer: `research/timing/2026-11-10-pre-event-direction/study.py`.

## Hypothesis

Information that is public before the 15:59 entry predicts the sign of the stock's
market-adjusted return across the announcement, by enough to clear a stock round trip. Five
trials, each with its own mechanism:

- **D1, pre-event reversal.** Names that fell over the three sessions before the pre-announcement
  session rise across the announcement, and the reverse. Liquidity providers demand a larger
  concession to hold inventory into scheduled news (So and Wang, JFE 2014).
- **D2, consumer demand.** Names with high card-spend and app-usage growth beat expectations
  (Carbon Arc demand score, built for another project; Froot et al., JFE 2017, for the mechanism).
- **D3, earnings seasonality.** Names whose reporting quarter is seasonally their strongest earn
  more at the announcement, because forecasts under-adjust for seasonality (Chang, Hartzmark,
  Solomon and Soltes, RFS 2017).
- **D4, revision breadth.** Names with more upward than downward estimate revisions before the
  release earn more at the announcement.
- **D5, composite.** The equal-weight average of the oriented signals above predicts the sign.

## Data and blocks

- Events: `outputs/research/ml_zoo/events_full.parquet` (11,257 rows, 2013-04 to 2026-08),
  de-duplicated on ticker and entry date. `entry_date` is the last close before the announcement
  and `exit_date` the reaction close.
- Prices: Yahoo adjusted closes for each ticker and SPY, the source validated against CRSP in the
  hedged-hold study. Names with no Yahoo history are unscored and counted.
- D2: `data/cache/carbonarc/ca_demand.parquet` (permno, eom, score; 2017-03 to 2026-10). Current
  vintage, not point-in-time, survivors only; a full month of publication lag is already imposed
  in the file. Permno from `outputs/research/2026-10-20-hedged-hold/features.parquet`.
- D3, D4: `tr_ibes.statsum_epsus` (statpers to 2026-01-15), linked through
  `wrdsapps_link_crsp_ibes.ibcrsphist`.
- Blocks by exit date. D1, D3, D4, D5: discovery 2013-18, validation 2019-24, confirmation
  2025-26. D2: discovery 2017-20, validation 2021-24, confirmation 2025-26.
- Outcomes viewed before: announcement returns on these events were scored conditional on the
  size of the reaction itself (gap fade, gap continuation, implied-surprise drift, all failed) and
  on option-derived features (put skew, parity forward). `ret_5d` was a feature of the model zoo,
  whose outcome was option P&L, not the stock return. No stock return on these events has been
  split by any of the five signals here. The Carbon Arc members were chosen on 2017-20 monthly
  returns in the other project, so the D2 discovery block is not clean; its validation and
  confirmation blocks carry the weight.

## Specification

Let `e` index the entry session and `x` the exit session in the name's own price series, `P` the
adjusted close and `M` the SPY adjusted close.

- **One-night outcome** (D2 to D5): `R = P[x]/P[e] - 1 - (M[x]/M[e] - 1)`.
- **D1 signal and outcome.** Formation `F = P[e-1]/P[e-4] - 1 - (M[e-1]/M[e-4] - 1)`. Position
  opened at the close of session `e-1` and closed at `x`:
  `R1 = P[x]/P[e-1] - 1 - (M[x]/M[e-1] - 1)`. The window follows So and Wang (formation t-4 to
  t-2, holding from t-1), with the exact session calendar replacing their three-day window. Not
  swept.
- **D2 signal.** `ca_demand` at the latest `eom` strictly before the entry date and no more than
  62 days before it.
- **D3 signal.** For the fiscal quarter being reported (the latest `fpedats` before the
  announcement date with a `statpers` before entry), take the 20 preceding fiscal quarters with a
  recorded `actual` announced before entry, all 20 required and the oldest no more than 5.5 years
  before the reported quarter's end. Rank the 20 actuals from 1 (lowest) to 20, ties averaged. The
  signal is the mean rank of lags 4, 8, 12, 16 and 20, the same fiscal quarter in earlier years.
- **D4 signal.** `(numup - numdown) / numest` at the latest `statpers` strictly before entry and
  no more than 40 days before it, for the quarter being reported, `numest` at least 3.
- **Bins.** Each signal is cut into causal quintiles with `hedged_hold.causal_bins` (breakpoints
  from events on strictly earlier dates, 200-event burn-in, the project's standing rule).
- **Positions.** D1: long the bottom quintile of `F`, short the top. D2, D3, D4: long the top
  quintile of the signal, short the bottom. Middle quintiles are not traded.
- **D5.** For each event, orient each signal's bin as `(bin - 2) / 2`, with D1 reversed so that a
  positive value means long. The composite is the mean over the signals that are defined, at least
  two required. Causal quintiles of the composite; long the top, short the bottom; one-night
  outcome.
- **Cost.** 12 basis points per position, round trip, stock and hedge together (the figure used in
  the implied-surprise drift study). Net return per position `= s x outcome - 0.0012`, `s` the
  position sign.

## Primary statistic and inference

Mean net return per position, as a fraction of stock notional, over all long and short positions
of the trial in the block. Date-clustered bootstrap on exit date, 5,000 draws, seed 0. Per-trade
Sharpe reported beside it. Secondary, reported and unable to rescue a failure: long and short legs
separately; D1 on the one-night window; megacap and broad names separately; the gross mean.

## Success criterion

Per trial, in order: discovery interval lower bound above zero; then validation interval lower
bound above zero; then confirmation mean above zero, reported with its interval. A trial that
passes all three is a pass.

## Kill criterion

A trial whose discovery interval lower bound is at or below zero is closed and its later blocks
are not scored. A trial that passes discovery and fails validation is closed. An interval wholly
below zero is reported as the opposite sign and is not rescued by reversing the position.

## Trial accounting

Five trials, D1 to D5, numbered 1,593 to 1,597 after the last record of 1,592
(`prereg_2026-11-09-combined-levers-hedged-hold.json`). No trial can rescue another.
