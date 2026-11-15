# Delta-hedged short straddles held to expiry, and the HAR and GARCH selectors

Draft for the analyst's signature. The numbers and the verdict lines apply the frozen criteria
mechanically; the interpretation paragraphs are proposed wording.

## Hypothesis, scope and success criteria

Selling the at-the-money straddle at the bid, hedging delta daily in the stock and holding to
expiry pays one option half-spread instead of the two that sink the next-session book, and
collects both the announcement premium (pre-event) and the diffusive variance premium. Four
first-wave trials (S1 pre-event 20-45 days, S2 post-event 14-45 days, S3a and S3b HAR selectors on
each) and three second-wave trials (W2a S1 at 46-120 days, W2b S2 selected by the post-event term
slope, W2c GARCH(1,1) with an announcement dummy on the S3b arm). Pre-registration
`prereg.md` (SHA-256 ada873df...), second wave `prereg_amendment_01.md` (a371d8a4..., frozen after
S1 and S3a were viewed and before any S2 or second-wave outcome). Pass: discovery (entry dates
2013-2018) lower bound above zero, then the same on validation (2019-2024); selectors also needed
the top tercile at the 95th percentile of the matched random null. Data: OPRA 15:59 ET chains
(Databento cache), CRSP daily stock file. Real data throughout.

## Results (discovery, 2013-2018; no candidate reached validation)

Books: mean net return on margin per trade, at the touch (sold at the bid), net of equity hedge
costs and fees, settled at intrinsic; intervals cluster on expiry date.

| Book | N | Mean net RoM | 95% CI | Per-trade Sharpe | At the mid | Entry half-spread / premium (median) | Implied minus realised (vol pts) |
|---|---|---|---|---|---|---|---|
| S1 pre-event, 20-45 days | 2,230 | -0.36% | [-0.59%, -0.14%] | -0.099 [-0.158, -0.041] | +0.36% | 4.5% | +2.66 |
| S2 post-event, 14-45 days | 2,604 | -0.36% | [-0.53%, -0.19%] | -0.149 [-0.217, -0.079] | +0.42% | 6.0% | +2.32 |
| W2a pre-event, 46-120 days (median 57) | 2,428 | -0.39% | [-0.73%, -0.10%] | -0.114 [-0.204, -0.028] | +0.40% | 3.9% | +1.52 |

DSR against 1,539 (first wave) and 1,542 (second wave) trials: 0.000 for every book.

Selectors: outcome net volatility points per unit vega, top minus bottom causal tercile.

| Selector | Assigned | Top minus bottom | 95% CI | Top tercile net RoM | Matched-null percentile |
|---|---|---|---|---|---|
| S3a HAR on S1 | 1,946 | -0.73 | [-2.08, +0.67] | -0.45% | 16.5 |
| S3b HAR on S2 | 2,366 | +0.04 | [-1.07, +1.07] | -0.40% | 31.2 |
| W2b post-event slope on S2 | 2,397 | +0.16 | [-0.88, +1.12] | -0.28% | 90.5 |
| W2c GARCH on S2 | 2,258 | -0.00 | [-1.20, +1.09] | -0.38% | 27.7 |

## Attrition

S1 kept 6,934 of 9,568 events in the blocks (2,631 without a quote in the window, mostly no
cached chain; 1 split or distribution; 1 incomplete path). S2 kept 7,711 (1,853 without a quote).
Kept events moved more on the reaction day than dropped ones (median absolute reaction 3.00% vs
2.65%, Mann-Whitney p = 2e-6 for S1; 2.95% vs 2.72%, p = 0.02 for S2). Larger moves hurt a short
straddle, so the attrition tilts against the book, not in its favour.

## Verdict

All seven fail discovery and are closed under the kill criterion; validation was not run.

The mechanism is present and the cost is still binding. Implied volatility exceeded realised by
1.5 to 2.7 points, and every book is positive at the mid with intervals clear of zero. Paying a
single half-spread (4 to 6% of premium) takes each of them below zero with intervals clear of zero
on the other side. Holding longer (W2a) lowers the spread share of premium but dilutes the event
premium by more. Neither a HAR nor a GARCH forecast of realised volatility, nor the post-event term
slope, separates the events that pay from those that do not. Selection on volatility forecasts is
closed on this book in the same way the 375-strategy zoo closed it on the next-session book.

## Files

`build_features.py`, `study.py`, `wave2.py`; outputs in `outputs/research/2026-10-20-hedged-hold/`
(`summary.json`, `summary_wave2.json`, per-event parquet files, not for commit).
