# Pre-registration: beta-hedged long of the most inverted post-event term structures, confirmation on 2025-2026

Frozen before any 2025-2026 stock return is downloaded. Record:
`outputs/research/prereg_2026-10-21-inversion-confirm.json`.
Scorer: `research/selection/2026-10-21-inversion-confirm/study.py`.

## Provenance of the hypothesis

Formed after viewing both 2013-2018 and 2019-2024, and says so. In the 2026-10-20 post-event
equity study and its 2026-10-21 follow-up, the lowest decile of the post-event term slope (the
14-45 day expiry richest relative to the expiry at least 21 days later, at the reaction
session's 15:59 ET close) outperformed in both blocks: +1.43% and +1.32% gross market-adjusted
over 20 trading days, and +1.27% and +0.98% gross after a CAPM beta adjustment (exploratory,
N=318 and 690). The pre-registered long-short tests failed (2013-18 with the wrong declared sign,
2019-24 at +0.37% [-0.29%, +1.02%]) because the highest decile also outperformed in 2019-24.
Neither block is out of sample for this hypothesis. The only untouched data is 2025-2026, and
this test is that one look.

## Hypothesis

Stocks in the lowest causal decile of the post-event term slope earn a positive CAPM-abnormal
return, net of costs, over the 20 trading days after the reaction session's close. Mechanism
(conjecture): a premium for bearing idiosyncratic uncertainty the option market says is still
unresolved after the announcement.

## Data and blocks

Events: `outputs/research/ml_zoo/events_full.parquet` with exit dates 2025-01-01 onward;
signal `post_slope` from `outputs/research/2026-10-20-hedged-hold/features.parquet` (OPRA 15:59
chains, Databento). Deciles: breakpoints from all events with strictly earlier exit dates since
2013, minimum 300, as in the source studies. Stock and market returns: yfinance adjusted closes
(split and dividend adjusted, so close-to-close ratios are total returns) for each name and for
SPY; risk-free rate the 13-week Treasury bill (yfinance `^IRX`, annual percent, divided by 100 and
by 252 per day). These sources are used only for outcomes and the hedge ratio, never for
selection.

## Specification

- Entry at the exit-date close, hold 20 trading days (the stock's own trading days in the
  download).
- Beta: OLS slope of the stock's daily excess return on SPY's over the 250 trading days ending at
  the exit date (minimum 200), from the same source.
- Outcome: compounded stock excess return minus beta times compounded SPY excess return.
- Cost: twice the name's median CRSP closing half-spread over 2024 (floored at 1 bp per side),
  plus 0.5 bp per side on the SPY hedge times |beta|. A name absent from CRSP in 2024 is dropped
  and counted.
- Funnel: every event without a signal, a decile, a full 20-day window or a beta is counted.

## Primary statistic and inference

Mean net CAPM-abnormal return per position in the lowest decile, per 20-day hold, cluster
bootstrap on exit dates, 5,000 draws, seed 0; per-position Sharpe; DSR against 1,544 trials. The
minimum detectable effect at this N is reported beside the result.

Secondary (reported, not pass criteria): the highest decile on the same basis, the long-short of
lowest minus highest, and every decile's mean.

## Success criterion

Lower bound of the primary interval above zero.

## Kill criterion

Lower bound at or below zero closes the idea. A positive point estimate with an interval through
zero is reported as inconclusive at this sample size, not as support.

## Trial accounting

One trial. Count after: 1,544.
