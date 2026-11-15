# Pre-registration: Wikipedia attention before the release as a selector for the hedged event hold

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-10-wikipedia-attention-hedged-hold.json`.
Scorer: `research/selection/2026-11-10-wikipedia-attention-hedged-hold/study.py`.

## Hypothesis

When public attention to a company spikes in the week before its release, retail option demand
pushes the event straddle above fair value, and the seller keeps more residual value per unit of
premium. de Silva, So and Smith (Review of Finance 2025) find that retail investors buy options
ahead of high expected-volatility announcements and lose on them. The closed IVOL and MAX
selectors proxied attention with prices; this measures it directly.

## Data and blocks

- Outcome, cells and loader: the hedged event hold, exactly as in
  `research/selection/2026-11-10-nonprice-selectors-hedged-hold`, whose module this study imports.
- Attention: daily page views of the company's English Wikipedia article from the Wikimedia
  pageviews API (all access, user agents only; available from 2015-07-01; free). Ticker to
  article from Wikidata's exchange-ticker statements, with 16 names resolved by hand and listed in
  `data/cache/wikipedia/ticker_article.csv` before any outcome is read. Views are keyed to the
  article's current title, so a renamed article loses its earlier history and those events are
  unscored and counted.
- Blocks by announcement date: discovery 2016-18, validation 2019-24, confirmation 2025-26.
- Outcomes viewed before: as in the imported study plus its results and those of the hackathon
  panels study. No outcome has been split by any attention measure other than IVOL and MAX.

## Specification

- `A = log(mean daily views over the 5 calendar days ending the day before the entry date /
  median daily views over the 60 calendar days before that window)`. At least 40 days with data in
  the 60-day baseline and all 5 in the window; a zero baseline median is unscored. Five days is the
  trading week before entry; sixty days stays inside the quarter and clear of the prior release.
  Not swept.
- Causal quintiles of `A` (`hedged_hold.causal_bins`, 200-event burn-in). Treated if in the top.

## Primary statistic and inference

Delta and the cell-matched null exactly as in the imported study; date-clustered bootstrap, 5,000
draws, seed 0.

## Success criterion

Discovery Delta interval lower bound above zero and null percentile at least 95; then the same on
validation; then confirmation Delta above zero and treated mean H above zero.

## Kill criterion

A miss on either discovery condition closes the idea. An interval wholly below zero is reported as
the opposite sign and is not rescued as a buyer's trade.

## Trial accounting

One trial, number 1,607.
