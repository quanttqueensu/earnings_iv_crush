# P1: pre-announcement put skew and the earnings-window stock return

## Hypothesis, scope and success criteria

**Hypothesis.** Traders with adverse private information buy out-of-the-money puts before an earnings release, so a steep pre-announcement put skew predicts a negative market-adjusted stock return over the announcement window (Xing, Zhang and Zhao, JFQA 2010; Jin, Livnat and Zhang, JAR 2012). This version reads the skew from the 15:59 ET consolidated-quote snapshot on the entry session, on the front expiry that spans the event, at an interpolated 25-delta strike in forward-delta space, and starts the outcome at the entry close, which precedes the release.

**Scope.** The 2025-2026 broad block (2,037 session-aware events, 346 names, entries 2025-01 to 2026-06), one block, scored once. Signal: `skew = IV(25-delta put) - IV(ATM call)`, Black-76 on the quote mid with the put-call-parity forward. Outcome: stock return minus SPY return from the entry close to the close two sessions later (yfinance adjusted closes), per event. Deciles within calendar-month buckets of at least 50 events.

**Success criterion (pre-registered).** All of: Spearman of decile number against decile mean at or below -0.60; the decile-1 minus decile-10 gap net of 5 bp per side (0.20 points for the two-legged round trip) with a date-clustered 95% interval excluding zero and positive; the gross gap at or above the 95th percentile of a matched within-bucket permutation null. Kill if Spearman is above -0.60 or the net interval includes zero.

Pre-registration: `research/selection/preregs/p1_skew_reaction_prereg.md`, SHA-256 `183460d8c8ecebba20e20af5c233d3f6724934cb93da9f4a54d2376692ae9d14` (`outputs/research/prereg_p1_skew_reaction.json`), hashed before any price was loaded. The scorer verifies the hash before it runs. Trial 1,498 in the programme ledger.

## Funnel

| Step | Events |
|---|---|
| Event file | 2,037 |
| No entry chain on disk / empty chain | -32 / -2 |
| No parity forward (no strike with both legs inside the 50% spread cap) | -103 |
| No ATM call IV bracket | -42 |
| 25-delta never reached by usable puts (no extrapolation) | -261 |
| Signal formed | 1,597 |
| Exact duplicate calendar rows (SMCI 2025-02-25, JBHT 2026-04-15) | -2 |
| EDGAR shows the release before the 15:59 snapshot (LMT, MOS, UAL) | -3 |
| No yfinance history (CMA, CTRA, EA, EQR, FI; delisted or renamed) | -12 |
| **Scored** | **1,580** (326 names, 251 entry dates, 12 buckets) |

1,575 of the signal events carry an EDGAR 8-K match; the rest are kept on the calendar's timing. The duplicate-row removal was not written into the pre-registration; it is mechanical (two identical rows of the same event) and was applied before any outcome was viewed.

## Results

All returns are per event, market-adjusted (beta one), over the [0, +2] session window, in decimal (0.01 = one percentage point of stock return). Nothing is annualised.

| Decile | N | Mean skew (vol) | Mean return | Median | SD | Hit rate |
|---|---|---|---|---|---|---|
| 1 (flattest) | 163 | -0.0295 | -0.0149 | -0.0203 | 0.0871 | 39.3% |
| 2 | 157 | -0.0027 | +0.0047 | -0.0032 | 0.0722 | 48.4% |
| 3 | 159 | +0.0057 | +0.0010 | -0.0052 | 0.0749 | 42.1% |
| 4 | 156 | +0.0114 | -0.0006 | +0.0040 | 0.0807 | 51.9% |
| 5 | 158 | +0.0161 | +0.0044 | +0.0004 | 0.0681 | 50.6% |
| 6 | 158 | +0.0205 | -0.0024 | -0.0086 | 0.0685 | 47.5% |
| 7 | 160 | +0.0257 | -0.0035 | +0.0052 | 0.0666 | 52.5% |
| 8 | 155 | +0.0318 | +0.0015 | -0.0013 | 0.0689 | 49.7% |
| 9 | 161 | +0.0405 | -0.0060 | +0.0025 | 0.0618 | 51.6% |
| 10 (steepest) | 153 | +0.0714 | -0.0092 | -0.0011 | 0.0824 | 49.0% |

**Primary statistic.** Decile 1 minus decile 10: **-0.0058 gross, date-clustered 95% CI [-0.0230, +0.0118]; -0.0078 net of costs, CI [-0.0250, +0.0098]**, N = 1,580 (316 in the two extreme deciles), 5,000 draws, seed 0, clusters = entry date. The sign is opposite to the hypothesis: the flattest-skew decile has the worst mean return (-1.49 points, standard error about 0.68), not the best.

**Monotonicity.** Spearman (decile, decile mean) = -0.273, against the -0.60 bar.

**Matched null.** 1,000 within-bucket permutations: median gap +0.0006, 95th percentile +0.0143; the observed gross gap sits at the 22.9th percentile.

**Long-short book and deflation.** As a per-event series net of a 5 bp-per-side round trip on each leg (N = 316): mean -0.43 points per trade, per-trade Sharpe -0.050, date-clustered CI [-0.157, +0.056]. Deflated Sharpe ratio against 1,498 trials: 0.000 (trial-Sharpe dispersion 0.127 from the straddle trials, a different return type, so a guide rather than a gate).

**Secondary, descriptive only.**

| Variant | N | Gap gross | 95% CI (gross) | Spearman |
|---|---|---|---|---|
| Pooled deciles | 1,580 | -0.0114 | [-0.0288, +0.0055] | -0.115 |
| EDGAR-matched only | 1,572 | -0.0064 | [-0.0237, +0.0116] | -0.333 |
| [0, +1] window | 1,580 | -0.0065 | [-0.0225, +0.0100] | -0.079 |
| BMO only | 901 | -0.0095 | [-0.0316, +0.0119] | -0.103 |
| AMC only | 679 | -0.0012 | [-0.0286, +0.0264] | -0.152 |
| Placebo [-3, 0] | 1,580 | +0.0095 | [+0.0008, +0.0187] | -0.685 |

No variant has the predicted sign with an interval excluding zero. The placebo row is the pre-entry window and is read differently below.

## Verdict against the kill rule

**FAIL on both kill conditions.** (a) Spearman -0.273 is above -0.60, so there is no monotone ordering; (b) the net gap's interval [-0.0250, +0.0098] includes zero. The gap is also inside the matched null (22.9th percentile). The pre-announcement 25-delta put skew, measured this way on this block, does not predict the earnings-window stock return, and the point estimate has the wrong sign.

The placebo gap is larger than the announcement gap. That is the expected contemporaneous relation, not predictability: stocks that fell over the three sessions before entry carry steeper put skew at entry (decile 10's pre-entry return is -1.01 points against -0.06 for decile 1). Skew is reacting to past returns, which is why the primary sort is within month rather than pooled.

Power was stated before the result: a minimum detectable gap of about 2 points per event. The realised clustered interval is about plus or minus 1.7 points, so a true gap below about 1.5 points in the predicted direction is not excluded by this block. What is excluded is a gap of the size that would pay for itself after costs in a single block.

## First practitioner objections

**Look-ahead: the 15:59 skew against an AMC print.** For AMC events the snapshot is on the announcement day at 15:59 and the release follows the close, so the signal precedes the news. The risk is a mislabelled session. The EDGAR 8-K checker (`outputs/research/edgar_sessions/`) matched 1,575 of the 1,597 signal events and found three whose 8-K was accepted before 15:59 on the entry day (LMT, a BMO filer labelled AMC; MOS, an intraday filing; UAL, accepted seven seconds before 16:00); they were excluded as pre-registered. Any residual look-ahead would favour the hypothesis, and the result is a fail regardless.

**Survivorship in the chain cache.** The universe was fixed from January 2024 information (S&P 500 constituents), before the block starts. Two losses are not neutral: five names with no yfinance history (12 events) and 408 events where the cached chain could not form a 25-delta skew under the spread cap. The second set leans toward less liquid names with sparse strikes, so the result describes names with a quotable 25-delta put.

**Short sample.** One block of 18 months, 251 entry dates, 316 events in the two extreme deciles. The DoltHub 2019-2024 chain is the planned second block and was not run; its nearest expiry is a median 16 days out with end-of-day marks, so its skew would be a different construction needing its own pre-registration. Given a fail with the wrong sign here, it is not a priority.

**Other objections.** Costs of 5 bp per side do not change the verdict, since the gross gap already fails. The effect is published and crowded, so post-publication decay is the expected outcome. A level-scaled skew was not tested and would be a new trial.

## Reproduction

```
python -m earnings_iv_crush.data.edgar_sessions
python scripts/research_p1_skew_reaction.py --stage all
```
