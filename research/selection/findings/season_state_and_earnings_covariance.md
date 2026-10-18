# Pivot experiments: season state and earnings covariance

Two pre-registered first-stage tests of the two cheapest directions proposed after the
single-name selection axis closed. Both are negative. Neither justifies acquiring new data.

Pre-registrations, frozen before the respective runs and verified byte-identical when
reported:

| File | SHA-256 |
|---|---|
| `season_state_prereg.md` | `c5abc0478f7b97a3a3a5cb88fe27f0907904e8ef3611d7571ff765c39cb2c154` |
| `earnings_covariance_prereg.md` | `e3e3f78f0d27e26c45f9f98efb29b5be3d7f0004f64df3ae1d7b13b1857b8852` |
| `earnings_covariance_prereg_amendment_01.md` | `c8a65e318ae9da452ab459387978d1bb49587b372dc836bdcd894cd2de008af0` |

---

## 1. Sequential earnings-season state

**Hypothesis.** Each earnings season carries a latent shock intensity the option market
does not know at the start of the season. Reporters who have already printed inside a
season are a causal read on it, so the average realised-versus-implied error of prior
same-season events predicts the executable return of the next short straddle.

**State variable.** For event *j* in season *q*, over strictly prior events in the same
calendar quarter, `S = mean( |realised move| / implied move - 1 )`. Minimum five priors.
Season is the calendar quarter of the announce date, fixed in advance.

**Payoff.** Executable return on margin, two-leg 15:59 consolidated-quote marks on the
entry and exit sessions, gross and net of the measured fixed-boundary cost model
(1.2714% entry, 3.0182% exit, of premium).

**Specification.** `R = alpha + beta * S + e`, single predictor, no controls. Both series
winsorised at the 1st and 99th percentile within window. Five thousand bootstrap draws,
seed 0, refitting the slope inside each draw.

### Result

| Block | Arm | N | Seasons | beta | Season CI | Name CI | Two-way CI | R² |
|---|---|---|---|---|---|---|---|---|
| 2019-2024 | gross | 708 | 24 | **-0.0334** | [-0.1085, +0.0596] | [-0.0989, +0.0231] | [-0.1182, +0.0513] | 0.0017 |
| 2022-2024 | gross | 365 | 12 | +0.0138 | [-0.0475, +0.0875] | [-0.0853, +0.1171] | [-0.0622, +0.0897] | 0.0002 |
| 2013-2018 | gross | 826 | 23 | **+0.0916** | [+0.0383, +0.1619] | [+0.0241, +0.1595] | [+0.0171, +0.1661] | 0.0129 |
| 2019-2024 | measured | 708 | 24 | -0.0340 | [-0.1106, +0.0621] | [-0.1015, +0.0240] | [-0.1210, +0.0530] | 0.0017 |
| 2013-2018 | measured | 826 | 23 | +0.0943 | [+0.0389, +0.1665] | [+0.0251, +0.1645] | [+0.0177, +0.1710] | 0.0129 |

Pre-registered decision rule:

1. Same slope sign in both disjoint blocks, **fails**. 2019-2024 gives -0.0334, 2013-2018
   gives +0.0916.
2. Season-clustered interval excludes zero in 2019-2024, **fails**, [-0.1085, +0.0596].
3. Sign not created by the cost model, passes. Cost moves the slope by less than 0.003 in
   both blocks, as expected of a charge applied to every observation.

**Verdict: not supported.**

### Reading

The only slope whose interval excludes zero is 2013-2018, and it does so under all three
clusterings. It is also the block whose sign the other block contradicts. A positive slope
in 2013-2018 means a violent season so far predicts *better* subsequent short-straddle
returns, so the market over-corrects within a season. A negative slope in 2019-2024 means
season violence persists. These are opposite economic mechanisms, not different magnitudes
of the same one.

Two readings survive and the data does not separate them. Either the 2013-2018 result is
sampling noise across 23 season clusters, which is the parsimonious reading given R² of
0.0129 and the sign flip, or season-state dependence is real but its own sign is regime
dependent, in which case it is not tradable without knowing the regime, which is the
original problem one level up.

The binding constraint is season count, not event count. Twenty-four clusters is the
effective sample size, and it was stated in the pre-registration that a wide interval here
should be read as low power rather than as evidence of absence. Roughly 165 of 873 scorable
events in the 2019-2024 block were unmarkable or sized to zero contracts and are excluded;
the same funnel is 81 of 907 in 2013-2018.

---

## 2. Physical earnings covariance

**Hypothesis.** Individual earnings event variance appears to be priced efficiently. The
untested object is the covariance term of the index variance identity: when several
economically linked firms report inside the same short window, their prints reveal common
information and residual co-movement should rise beyond what individual jump variances
imply.

**Data.** CRSP daily panel and the IBES/Compustat announcement panel, 2010-2024. Top 500
US common stocks by market capitalisation ranked on the prior year-end and held fixed for
the following year, with weights from the same snapshot. Roughly 1.86 million name-days and
23,691 announcements carrying a causal expected event variance. **No option data.**

**Load.** `EIL = sum over reporters of w_i^2 * J_i`, with `J_i` the causal expanding mean
of that name's prior squared day-0 excess returns, minimum four priors.

### 2a. The first specification was defective and its output is discarded

The original outcome was the cross term of a portfolio of market-model residuals. That
construction is degenerate: the cap-weighted top 500 *is*, to close approximation, the
market factor, so cap-weighting residuals taken against that factor produces a near-zero
portfolio and the cross term collapses to minus the own-variance term.

Measured, not argued. The daily residual portfolio has standard deviation 0.001207 against
0.016900 for a typical single name, a factor of fourteen. Its mean squared value is
1.458e-06 against a mean own-variance term of 1.574e-06, a ratio of 0.926.

| Regressand | Slope on EIL | Correlation |
|---|---|---|
| `own` = sum w² r² | +0.9587 | +0.4745 |
| `R²` = residual portfolio variance | +0.2302 | +0.0593 |
| `C = R² - own`, the reported outcome | **-0.7285** | -0.2120 |

The reported slope is the exact difference of the other two. The load predicts individual
event variance well, which is what it is built to do; it barely predicts the residual
portfolio's variance, because that portfolio is degenerate; and the subtraction turns the
first fact into an apparent covariance finding. The defect is provable a priori from the
fact that the residualising factor and the aggregation weights describe the same portfolio,
so the run is discarded rather than reported, and is not charged as a trial.

### 2b. Corrected specification

Excess returns throughout, no residualisation. The outcome is the dispersion desk's
correlation measure applied to realised rather than implied variances, over a window:

    rho = ( V_index - sum_i w_i^2 v_i ) / ( ( sum_i w_i sqrt(v_i) )^2 - sum_i w_i^2 v_i )

Dividing by the correlation-of-one denominator is what makes this a correlation test.
Undivided, weighted own variance is a small fraction of index variance and the regression
would be answering whether earnings season is a high-volatility period. It is, and that is
not the hypothesis.

Non-overlapping 5-trading-day windows (754 of them, 3-day tiling secondary), quarter-
clustered bootstrap as primary inference, 5,000 draws, seed 0. Two-sided, with both signs
interpreted in advance.

### Result

Mean realised correlation across windows is 0.3364 with standard deviation 0.2010.

| Specification | N | Quarters | beta on EIL | Quarter CI | R² |
|---|---|---|---|---|---|
| univariate | 754 | 60 | **-5,259** | [-8,329, -2,993] | 0.0146 |
| + reporter count | 754 | 60 | **+315** | [-2,877, +3,498] | 0.0393 |
| + market variance | 754 | 60 | -5,236 | [-8,246, -3,320] | 0.2264 |
| + all controls | 754 | 60 | **+580** | [-4,231, +4,649] | 0.2455 |
| rank load (secondary) | 754 | 60 | -0.147 | [-0.202, -0.094] | 0.0447 |
| sub-period 2010-2016 | 353 | 28 | -31,563 | [-44,290, -19,407] | 0.0545 |
| sub-period 2017-2024 | 401 | 32 | -2,642 | [-4,756, -699] | 0.0068 |
| bellwether windows | 151 | 56 | -1,168 | [-4,318, +1,659] | 0.0032 |

Pre-registered decision rule:

1. Quarter-clustered interval excludes zero, pooled 5-day, **passes**, negative sign.
2. Same sign in both sub-periods, **passes**.
3. Survives the controls, market variance in particular, **fails**. The market-variance
   control leaves the slope intact at -5,236. The reporter-count control destroys it:
   +315 with an interval of [-2,877, +3,498].

**Verdict: the firm-identity-weighted covariance hypothesis is killed at the physical stage.
Reporter count survives as a sufficient calendar statistic for the measured physical
correlation effect.** The distinction matters: what died is the claim that *which* firms report,
weighted by anticipated event importance, adds information beyond *how many* report. The
correlation effect itself is real, large, and reported below.

### Reading

The correlation effect is real and economically large. Realised correlation falls
monotonically with earnings activity:

| Reporter-count quintile | N | Mean reporters | Mean realised correlation |
|---|---|---|---|
| Q1 fewest | 158 | 1.4 | 0.4064 |
| Q2 | 161 | 5.4 | 0.3358 |
| Q3 | 142 | 11.5 | 0.3483 |
| Q4 | 144 | 36.0 | 0.3086 |
| Q5 most | 149 | 106.0 | 0.2783 |

A drop of 0.128 in realised correlation from the quietest to the busiest windows. The sign
is negative, which contradicts the common-information hypothesis and supports the opposing
reading: earnings are firm-specific information events, names move on their own news, and
index correlation falls during earnings season.

**The driver is the reporter count, not the earnings load.** Regressing realised
correlation on the count alone gives R² of 0.0393; adding the load leaves R² at 0.0393 to
four decimal places and the load's own slope indistinguishable from zero. The load quintile
table reproduces the count table only because the two variables are nearly the same thing:
the heaviest-load quintile averages 94 reporters against 1.8 in the lightest.

That is the pre-registered kill condition, stated before the run: an effect carried purely
by how many names report is a calendar variable visible to every participant months in
advance, so there is no reason for the option market to miss it. The bellwether test points
the same way. Windows in the top quintile of reporting weight share, where the
common-information story should be strongest, give a slope whose interval contains zero and
an R² of 0.0032.

Independently, the direction found is the one that is already traded. Falling implied
correlation into earnings season is the standard long-dispersion expression and practitioner
commentary treats it as routine (sources below are practitioner rather than peer-reviewed,
and no academic confirmation of the earnings-season index-correlation effect was located).
An option-stage test would therefore have to establish that the market moves implied
correlation by the wrong *amount*, against a crowded trade, which is a far higher bar than
the physical test this was designed to be a cheap precursor to.

**Consequence, per the pre-registration.** No index or ETF option data is acquired. The
QQQ-versus-SPY relative-variance implementation is not built.

---

## Trial accounting

Two trials charged: season state, and the corrected earnings correlation. The defective
covariance specification is not charged, on the ground that its output is discarded and no
inference is drawn from it in either direction; the original file and the amendment are
both retained so that the discard is auditable rather than asserted.

## Sources

Practitioner commentary on earnings season and implied correlation:
Investing.com, "Volatility Dispersion Trade Unwind Likely Ahead of Key Earnings";
Resonanz Capital, "Dispersion Trading and the DSPX Index";
Interactive Brokers Quant, "Dispersion Trading in Practice".
