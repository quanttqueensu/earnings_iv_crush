# Pivot test verdicts

Results from the zero-spend screening programme. Each entry records the achieved N, the
basis of every figure, and the honest verdict including inconclusive ones. All data from
the WRDS R2 mirror, CBOE and cached local files. No metered spend.

Harness validated before any candidate was scored: re-scoring the settled IV-crush book
through `engine.screen` reproduces N=391, per-trade Sharpe +0.055992 and clustered 95% CI
[-0.0421, +0.1803], matching `paper/iv_crush_verdict.tex` on all four figures
(`scripts/validate_screen.py`).

---

## #3 Index VRP timing: **negative out of sample**

**Run:** `scripts/pivot_vrp_timing.py`. **Output:** `outputs/research/pivot/vrp_timing.csv`.
**Trials:** 15 specifications pre-registered in `outputs/research/pivot/trial_ledger.json`
before any was run.

### Specification

Variance risk premium as squared VIX minus realised variance, monthly, following
Bollerslev, Tauchen and Zhou (2009). Predictive regression of forward cumulative excess
returns on the VRP at horizons of 1, 3, 6, 12 and 24 months. Panel of 420 months, 1990-01
to 2024-12. Data: CBOE VIX (`cboe_all.cboe`), S&P 500 level and return (`crsp_a_stock.dsi`),
risk-free rate (`ff_all.factors_daily`).

Two stated deviations from the source. Realised variance is built from **daily** rather
than five-minute returns, which BTZ state their results depend crucially on; the daily
estimator is noisier, so results here are attenuated by construction. Standard errors are
Newey-West at lag equal to the horizon rather than Hodrick (1992), which is the less
conservative choice, so the t-statistics should be read as an upper bound.

### Result

| Window | h=1m | h=3m | h=6m | h=12m | h=24m |
| --- | --- | --- | --- | --- | --- |
| **Original 1990-2007** (N=216) | t +1.69, R² 0.96% | **t +3.67, R² 5.41%** | t +3.20, R² 5.26% | t +1.80, R² 2.50% | t +1.53, R² 1.18% |
| **Extended 1990-2024** (N≈415) | t +0.36, R² 0.06% | t +0.70, R² 1.18% | t +0.54, R² 0.28% | t -0.50, R² -0.08% | t -1.04, R² 0.16% |
| **Post-sample 2008-2024** (N≈195) | t +0.24, R² -0.27% | t +0.50, R² 0.72% | t +0.30, R² -0.26% | t -1.03, R² 0.44% | t -1.42, R² 1.86% |

All R² are adjusted. All t-statistics are Newey-West.

**The original window replicates.** The quarterly horizon is the peak, at t = +3.67 and
adjusted R² 5.41%, against BTZ's reported t = 2.86 and R² 6.82%. The point estimate is
attenuated exactly as the daily-realised-variance substitution predicts, and the shape of
the horizon profile matches. This is the harness validation: the screen recovers a
documented effect on the window where it was documented.

**The effect does not survive.** Extending to 2024 collapses the quarterly t-statistic from
+3.67 to +0.70 and the R² from 5.41% to 1.18%. On the clean post-sample block, 2008 to 2024,
nothing is significant at any horizon and the slope turns **negative** at 12 and 24 months.

### The placebo check

Boudoukh, Richardson and Whitelaw argue that R² rises with horizon by construction when a
persistent predictor meets overlapping returns. BTZ acknowledge this without neutralising
it. Each cell was therefore re-run against 200 AR(1) placebo predictors matched to the VRP's
own persistence but independent of returns.

On the original window the real R² clears the placebo 95th percentile at every horizon
except 24 months, so the in-sample finding is not merely an overlap artefact. On the
post-sample block **no horizon clears its placebo band**. The one apparent exception is the
extended-window 3-month cell, where R² 1.18% exceeds the placebo p95 of 0.90% while the
t-statistic is only +0.70; that is a reminder that R² and slope significance can disagree
under overlap, and the insignificant slope is the figure to believe.

### Verdict

The index variance risk premium predicted market returns over 1990-2007 and does not
predict them over 2008-2024. Sign instability at the long horizons, rather than mere
attenuation, is the strongest evidence against a surviving effect: a decayed but real
premium would shrink toward zero, not flip.

Two caveats bound this conclusion. The daily realised-variance substitution attenuates the
measured relationship in every window, including the post-sample block, so some of the
collapse is measurement rather than decay. And a 17-year post-sample block at monthly
frequency is not a large sample. What the result rules out is a VRP timing signal strong
enough to be worth building on with the data available here.

**Disposition: do not pursue as a standalone strategy.** The panel and the harness are
retained; `outputs/research/pivot/vrp_panel.csv` is a reusable monthly VRP series.

---

## #1 PEAD / SUE: **directionally positive out of sample, not established**

**Run:** `research/off_earnings/research_pead_sue.py` (907s). **Outputs:** `outputs/research/pead_summary.csv`,
`pead_decile_car.csv`, `pead_fama_macbeth.csv`, `pead_daily.csv`, `pead_decile.png`.

Primary specification frozen before this programme began: long decile 10 / short decile 1 of
SUE, breakpoints from the four completed calendar quarters strictly before the event's own
quarter, entered at day0+1, held 60 trading days, overlapping cohorts, equal-weighted, net
of round-trip equity cost. Fit 1996-2011 sets nothing; holdout 2012-2024 is the only test
that counts.

### Result

| Basis | Period | N trades | Hit rate | Mean trade | Calendar-time Sharpe (ann.) | FF4 alpha (ann.) | NW t | Median cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| net | fit 1996-2011 | 19,214 | 50.5% | -0.000936 | **-0.201** | -2.52% | -1.61 | 28.1 bps |
| net | **holdout 2012-2024** | 19,620 | 51.1% | +0.006267 | **+0.545** | +2.51% | +1.65 | 16.2 bps |
| gross | holdout 2012-2024 | 19,620 | 51.6% | +0.008232 | +0.692 | +3.39% | +2.23 | n/a |

The annualisation factor here is √252 and that is **correct**, unlike the event-book case:
overlapping cohorts produce a genuine daily calendar-time return series (3,269 daily
observations in the holdout, roughly 13 years of trading days), not a sparse per-trade
series. This is the same factor that was wrong before, applied to a case where it is right.

### The tension in the evidence, and how to read it

Three tests disagree, and the disagreement is the finding.

- The **date-clustered bootstrap on mean net return** gives a holdout interval of
  [+0.00306, +0.00960], which **excludes zero**.
- The **Fama-French-Carhart alpha** on the calendar-time series gives t = +1.65 net, which
  does **not** clear 5%. Gross it reaches t = +2.23.
- The **Deflated Sharpe Ratio** against the 16 trials in the K-sweep and secondary cuts is
  **0.0597**, which is very low.

The bootstrap treats each trade as a unit and so overstates precision on a book with
overlapping 60-day holds and heavy announcement-date clustering. The calendar-time FF4
alpha is the more appropriate test because it prices factor exposure and handles the
overlap, and it does not clear. The DSR settles it: against the search actually made, a
holdout Sharpe of this size is consistent with the best of a no-edge family.

### What is genuinely unusual

**The sign flips the right way.** The fit period is negative (-0.201 annualised) and the
holdout positive (+0.545). That is the opposite of the classic overfitting signature, where
the fit sample looks good and the holdout collapses. Nothing was tuned on the fit sample, so
this is not a fitted result that failed to generalise; it is a specification that did
nothing for fifteen years and then did something for thirteen.

Two readings, and the evidence does not separate them. Either PEAD genuinely strengthened
post-2012, which runs against the published consensus that the anomaly has decayed, or the
holdout block is a lucky draw, which the DSR of 0.0597 says is entirely plausible. The
honest position is the second, with the first left open.

Costs nearly halved between periods (28.1 to 16.2 bps median round-trip), which is a real
and well-documented feature of US equity execution over that span rather than an artefact.
Some of the fit-to-holdout improvement is therefore cost compression rather than signal.

### Verdict

Directionally positive out of sample on a genuinely pre-registered specification, and not
statistically established. A net calendar-time Sharpe of +0.545 is economically interesting
and the gross FF4 alpha does clear at t = +2.23, so this is the strongest candidate found so
far. It is not investable on this evidence.

**Disposition: keep, and attack the DSR rather than the point estimate.** The trial count of
16 is what is killing it. A single pre-declared specification tested on data not yet touched
would carry far less deflation than a K-sweep. The natural next step is to freeze K=60 and
the SUE-sigma construction now and test only that, once, on a future block.

### One engineering change, recorded for transparency

The daily panel is 27,076,941 rows by 21 columns and needs a >2 GB allocation that fails on
this machine (15.2 GB total, 3.0 GB free). The loader now projects to the eight columns any
calculation actually reads and downcasts them; `smb`, `hml` and `umd` are read separately
and deduplicated to one row per date, which is how `_ff_frame` consumed them anyway. No row
is dropped and no column any calculation touches is excluded, so the specification is
unchanged.

One change was required to run it, and it is a memory fix rather than a specification
change. The daily panel is 27,076,941 rows by 21 columns and needs a >2 GB allocation that
fails on this machine (15.2 GB total, 3.0 GB free). The loader now projects to the eight
columns any calculation actually reads and downcasts them; `smb`, `hml` and `umd` are read
separately and deduplicated to one row per date, which is how `_ff_frame` consumed them
anyway. No row is dropped and no column that any calculation touches is excluded.

---

## #6 IV term-structure slope, de-eventised: **blocked on free data as specified**

**Not run.** The free DoltHub option database cannot support the published signal.

Vasquez defines the slope as `IV_LT - IV_1M`, long-term minus one-month at-the-money
implied volatility. Verified directly against the DoltHub API this session, the
`option_chain` table carries **exactly three expiries per snapshot**, consistently at
roughly 14, 28 and 49 days to expiry:

| Ticker | Snapshot | Expiries | DTE |
| --- | --- | --- | --- |
| AAPL | 2023-06-30 | 3 | 14, 28, 49 |
| AAPL | 2021-03-31 | 3 | 16, 30, 51 |
| MSFT | 2023-06-30 | 3 | 14, 28, 49 |
| XOM | 2022-09-30 | 3 | 14, 28, 49 |

There is no long-dated leg. The widest term spread constructible is 14 days against 49
days, which is a short-dated slope, not Vasquez's. Two further gaps confirmed at the same
time: the adapter returns no `spot` column, so the underlying must be joined from CRSP, and
`open_interest` is hard-coded to NaN, which independently confirms the dossier's exclusion
of any dealer-gamma or wing-demand candidate on free data.

**Disposition.** Three routes, in order of preference:

1. **Run the short-dated variant and label it as such.** A 14-versus-49-day slope is close
   to the IV-crush project's own front-week-minus-back-month construction, so it still
   separates "the term signal is empty" from "the earnings event was the problem", which is
   the question that matters. It is not a Vasquez replication and must not be reported as
   one.
2. **Use the local Databento cache** for a true long-dated slope on 50 names, already paid
   for, at the cost of a narrow cross-section that supports terciles at best.
3. **Defer** until a metered pull is authorised.

The builder and scorer are written, adapted to the 14/28/49-day reality, and validated end
to end at `research/off_earnings/pivot_vasquez_slope.py` (`--build --max-calls N`, then `--score`), with
mid-priced and full-touch arms scored side by side so the literature's cost assumption is
tested rather than inherited.

**Smoke test passed (8 calls, 6 usable).** Two constructions needed for the free path were
verified rather than assumed:

- **Spot recovered by put-call parity**, since the adapter returns no underlying. The strike
  minimising the call-put mid difference gave AAPL 172.5 and MSFT 111.0 on 2019-02-28, both
  within about a dollar of the actual closes.
- **The slope measures what it should.** AAPL on 2019-04-30, its reporting date, shows front
  IV 33.4% against back 23.8% for a slope of -9.5%: exactly the inverted term structure the
  IV-crush gate triggered on, now measured off the event calendar rather than on it.

One coverage note: 2019-01-31 returns empty chains for both names, so usable history starts
slightly later than the nominal 2019-01 start.

**Runtime.** The full 70-name, 70-month panel is roughly 4,900 HTTP calls at approximately
0.2/s, so about seven hours. This is an overnight job, not an interactive one. It is free,
checkpointed every 100 calls and resumable, so it can be run in bounded sessions.

---

## #13 Volatility information transfer: **not yet run**

Queued behind #6 because it needs the same broad option panel: the design requires a first
announcer per industry-quarter and peers reporting at least 10 trading days later, which the
50-name local cache cannot populate at 4-digit SIC granularity.
