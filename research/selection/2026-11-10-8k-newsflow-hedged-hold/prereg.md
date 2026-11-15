# Pre-registration: 8-K news flow before the release as a selector for the hedged event hold

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-10-8k-newsflow-hedged-hold.json`.
Scorer: `research/selection/2026-11-10-8k-newsflow-hedged-hold/study.py`.

## Hypothesis

Names that filed the most 8-Ks in the two months before a scheduled release have already
disclosed more of the quarter's news, so the release moves the stock less than the implied move
charges and the seller keeps more residual value per unit of premium. Heitz, Narayanamoorthy and
Zekhnini (2020, working paper) find announcement returns inversely related to prior 8-K filing
returns.

## Data and blocks

Outcome, cells, dates and the EDGAR `recent` arrays exactly as in
`research/selection/2026-11-10-nonprice-selectors-hedged-hold/prereg.md`, whose loader this study
imports. Blocks by announcement date: discovery 2019-21, validation 2022-24, confirmation
2025-26. Outcomes viewed before: as listed there, plus that study's five trials (V3 used Item 2.02
filings in the 3 to 44 day window; this feature excludes Item 2.02 filings).

## Specification

- Count `K`: filings with form `8-K` whose items do not include `2.02`, accepted between 60 and 3
  calendar days before the announcement date. Sixty days covers the quarter's close to the
  release without reaching the previous release; not swept.
- Scored only if the name's cached array starts at least 120 days before the announcement.
- Causal quintiles of `K` (`hedged_hold.causal_bins`, 200-event burn-in). Treated if in the top
  quintile.

## Primary statistic and inference

Delta and the cell-matched null exactly as in the non-price selectors study.

## Success criterion

Discovery Delta interval lower bound above zero and null percentile at least 95; then the same on
validation; then confirmation Delta above zero and treated mean H above zero.

## Kill criterion

A miss on either discovery condition closes the idea. An interval wholly below zero is reported as
the opposite sign and is not rescued.

## Trial accounting

One trial, number 1,603.
