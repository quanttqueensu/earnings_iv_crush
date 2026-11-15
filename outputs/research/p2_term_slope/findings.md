# P2: the de-eventised, short-dated term-structure slope

## Hypothesis, scope and success criteria

**Hypothesis.** Away from earnings announcements, the slope of the implied-volatility term structure predicts straddle returns: straddles on an upward-sloping structure (front cheap) earn more than straddles on a steep, front-heavy one (Vasquez, JFQA 2017). The earnings book sold straddles on that short leg and failed after costs; this test asks whether the slope carries anything once the announcement is removed, and whether a liquidity taker can keep it.

**Scope.** 70 fixed US large caps (`DEFAULT_UNIVERSE` in `scripts/pivot_vasquez_slope.py`), month-end formation January 2021 to August 2026 (68 months), free DoltHub chains. Signal: 49-day minus 14-day ATM implied volatility (DoltHub lists only about three expiries), so this is a **short-dated construction, not a Vasquez replication**. Trade: the middle-expiry (24 to 31 days, median 28) ATM straddle, bought or sold at the formation close and held to expiry, settled at intrinsic on the expiry close. Every name-month with an earnings announcement between formation and expiry is excluded. Quintile sort within month; long the top quintile, short the bottom.

**Success criterion (pre-registered).** The full-touch long-short mean per trade has a date-clustered 95% CI entirely above zero and beats the 95th percentile of a within-month permutation null. **Kill rule:** the full-touch interval includes zero.

Pre-registration `_private/p2_term_slope_prereg.md`, SHA-256 `3f399b6aa7c788a280840fab6fa0d5af52fec712b58c7b16dbb6ea55b506659a`, with two dated, hashed amendments, all recorded in `outputs/research/prereg_p2_term_slope.json`.

## Verdict

**Fail. The kill rule fires.** At the mid the slope sorts straddle returns in the predicted direction (long-short +8.77% of premium per trade, CI [-0.65%, +17.87%], quintile ordering Spearman +0.70, mechanism check passed). At the full touch the same trades lose -7.79% per trade, CI [-18.06%, +2.23%], which includes zero, and the observed figure sits at the 92.7th percentile of the matched null, below the required 95th. The short-dated de-eventised slope is not monetisable by a liquidity taker on this data, and P2 closes.

The median ATM straddle here carries a relative half-spread of 4.67% of mid (mean 6.78%, 90th percentile 12.9%), paid once on entry; the long-short pays it on both legs, which is roughly the 16.6-point gap between the two arms.

## Results

All returns are per trade, on straddle premium, over one holding period of about four weeks (not annualised). Long-leg return `(payoff - entry) / entry`; short-leg `(entry - payoff) / entry`; the touch arm buys at the ask and sells at the bid; settlement at intrinsic carries no further spread; commissions not charged. Intervals: percentile bootstrap resampling formation months, 5,000 draws, seed 0. N = 606 long-leg and 616 short-leg trades over 68 months.

| Arm | Long-short per trade | 95% CI | Long leg | Short leg | Long hit | Short hit | Monthly LS Sharpe |
|---|---|---|---|---|---|---|---|
| Mid | +8.77% | [-0.65%, +17.87%] | +7.54% | +1.23% | 45.4% | 58.4% | +0.238 |
| Full touch (primary) | **-7.79%** | **[-18.06%, +2.23%]** | +1.94% | -9.72% | 42.9% | 55.7% | -0.093 |

Matched null (slopes permuted across names within each month, 1,000 draws, touch arm): median -14.60%, 95th percentile -6.72%; the observed -7.79% is at the 92.7th percentile. The null centre is negative because a random long-short also pays the spread on both legs. Deflated Sharpe of the monthly touch series against 1,497 recorded trials: 0.000.

Quintile means of the long-straddle return, per trade (mean slope in decimal vol):

| Quintile | N | Mean slope | Mid | (se) | Touch | (se) |
|---|---|---|---|---|---|---|
| 0 (front-heavy) | 616 | -0.0160 | -1.23% | 3.10% | -7.54% | 2.93% |
| 1 | 583 | -0.0000 | +5.50% | 3.20% | -0.56% | 3.03% |
| 2 | 584 | +0.0075 | +6.31% | 3.42% | -0.09% | 3.23% |
| 3 | 583 | +0.0167 | +3.75% | 3.18% | -2.69% | 2.99% |
| 4 (upward) | 606 | +0.0429 | +7.54% | 3.56% | +1.94% | 3.42% |

The ordering is carried mainly by the bottom quintile being poor, not by a monotone ramp.

Clean-signal subsample (also excluding any announcement inside the back leg's 59-day window), N = 1,532 name-months: mid +2.21% [-11.58%, +15.53%], touch -15.15% [-29.89%, -0.58%]. Removing event contamination from the signal weakens the mid effect, which suggests part of the full-sample mid premium came from names with an announcement just past expiry.

## Funnel and data quality

| Step | Name-months |
|---|---|
| Universe x formation months | 4,760 |
| Formation snapshot not on the month's last session (stepped back, amendment 01) | 1,147 |
| No snapshot on any candidate session | -2 |
| Signal leg missing (no 7-20 or 35-59 day contracts near the money) | -118 |
| No middle expiry (21-34 days) | -141 |
| Split or spin-off inside the holding window (amendment 02) | -18 |
| Formation close disagrees with chain parity spot by more than 3% | -18 |
| Built | 4,463 |
| Earnings announcement inside the holding window | -1,491 |
| Scored (all 68 months, no month thinner than 10 names) | 2,972 |

DoltHub carries snapshots on only some sessions; every snapshot here was requested by exact date on NYSE sessions only, stepping back at most five calendar days from month-end and recording the date used (1,147 name-months formed one or two sessions early). The rotating weekly expiries do not affect this design: the straddle is held to expiry and settled on the underlying's close, so no exit snapshot is read. Earnings dates are the union of DoltHub `earnings_calendar` and Compustat `rdq` (R2 mirror, to 2026-06-23); after June 2026 only DoltHub covers the exclusion.

**A voided first run.** The first scoring settled straddles across splits on a post-split close against a pre-split strike (GE's 1-for-8 reverse split showed +10,130%; NFLX, WMT, AVGO, AMZN, GOOGL, NVDA and TSLA showed +480% to +1,281%). Its numbers were seen (touch long-short -26.8% per trade, CI [-68.2%, -0.9%]) and are void. Amendment 02 excludes name-months with a split or spin-off in the holding window, fixed before rerunning; the run above is the result, and it is not blind to the voided one.

## First objections

**Costs.** The touch arm is the honest basis for a taker and still generous: commissions and settlement costs are not charged. A maker-side version of this trade is a different, untested question.

**Short-dated construction.** The result says nothing about Vasquez's long-dated slope and is not a failed replication.

**Survivorship and universe.** The 70 names are today's large caps, chosen with hindsight; the bias runs through which names are compared rather than the level.

**Overlapping windows.** Consecutive formations are about a month apart and straddles expire 24 to 31 days after formation, so overlap is at most a few days; trades within a month are resampled together.

## Prior work

Vasquez (JFQA 2017); Goyal and Saretto (JFE 2009); Dubinsky, Johannes, Kaeck and Seeger (RFS 2019); Alexiou et al. (RoF 2025). This version excludes every name-month with an announcement in the holding window, uses a 14 against 49 day slope on free 2021-2026 data, and makes the full-touch arm primary.

## Reproduction

```
python scripts/research_p2_term_slope.py
```
