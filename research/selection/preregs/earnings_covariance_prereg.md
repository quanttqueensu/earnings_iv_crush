# Pre-registration: physical earnings covariance

Frozen before any regression is run. One trial. This is a **first-stage physical test**
and deliberately involves no option data at all. If the mechanism does not exist in the
underlying equities, no option-market mispricing of it can exist either, and no index or
ETF option data is acquired.

## Hypothesis

Individual earnings event variance appears to be priced efficiently: the project has tested
that object from eight directions and every one collapses under out-of-sample testing and
realistic execution. The untested object is the **second** term of the index variance
identity

    sigma_index^2 = sum_i w_i^2 sigma_i^2  +  2 sum_{i<j} w_i w_j sigma_i sigma_j rho_ij

Scheduled announcements are not independent draws. When several economically linked firms
report inside the same short window, their prints reveal common information, and the
residual co-movement of the index constituents over that window should rise beyond what
the individual jump variances alone imply.

The claim under test is narrow and physical: **does scheduled earnings concentration
predict subsequent realised residual covariance among index constituents?**

The null is that residual co-movement over a window is unrelated to how much scheduled
earnings information lands inside it.

## Universe and weights

Top **500** US common stocks by market capitalisation, ranked on the last trading day of
the **prior** calendar year and held fixed for the whole of the following year. Weights
`w_i` come from the same prior-year-end snapshot, normalised to sum to one, and are also
held fixed within the year. A fixed annual snapshot is used rather than daily weights so
that weight drift cannot itself co-move with returns.

Sample: **2010-2024**. Earlier CRSP history exists but the announcement panel's session
labelling is weakest in the 1990s.

## Residualisation

For each name and each calendar year, a market model is fitted on the **prior** calendar
year's daily excess returns, requiring at least 120 observations:

    r_it - rf_t = alpha_i + beta_i * mktrf_t + e_it

The residual return used throughout is

    r_perp_it = (r_it - rf_t) - beta_iy * mktrf_t

with `beta_iy` estimated strictly on prior-year data. Names without a fitted beta are
excluded from the universe for that year.

## Windows

Non-overlapping **5-trading-day** windows, tiled forward from the first trading day of
2010. Non-overlapping is chosen so that ordinary least squares is not fitting the same
returns repeatedly and so that the dependence structure is limited to within-season.

A 3-day tiling is reported as a **secondary** result. It is declared here so it cannot be
presented later as the primary if it happens to look better, and it is not permitted to
change the verdict.

## Earnings information load

For each name, the announcement's first affected trading session is taken from the panel's
existing session-aware `day0`, which already handles before-open and after-close prints.

The expected event variance of name *i* at announcement *k* is the causal expanding mean
of that name's own **prior** squared day-0 residual returns, requiring at least **4**
priors:

    J_hat_ik = mean over prior announcements m < k of ( r_perp_i,day0(m) )^2

The load on window *t* is

    EIL_t = sum over i reporting in t of  w_i^2 * J_hat_ik

Note this is deliberately built from the **variance** term. That is the point: the test
asks whether a quantity constructed entirely from individual event variances predicts the
**covariance** term, which nothing in the identity requires it to do.

## Realised residual covariance

For each trading day *d*, with `R_d = sum_i w_i r_perp_id` the residual portfolio return:

    C_d = R_d^2 - sum_i w_i^2 r_perp_id^2
    CoV_t = sum over d in window t of C_d

`C_d` is the exact cross-term of the portfolio variance decomposition, so a single isolated
jump in one name contributes **zero** to it by construction. That is the property that
makes this a covariance test rather than a restatement of the variance test.

## Primary specification

    CoV_t = a + b * EIL_t + e_t

pooled over 2010-2024. The hypothesis predicts `b > 0`.

## Controls declared in advance, not chosen after the fact

Three, each addressing a specific way the primary slope could be spurious:

1. **Reporter count.** `N_t`, the number of universe constituents reporting in the window.
   If the effect is only that more names reporting means more co-movement, the finding is
   mechanical and the option market, which sees the same calendar, has no reason to miss
   it.
2. **Market variance.** `sum over d in t of mktrf_d^2`. Beta is estimated with error, so
   residuals retain some market exposure; if market variance is itself higher during
   earnings season, that alone would produce a positive slope with no covariance content.
   This is the most dangerous of the three.
3. **Reporter weight share.** `sum over reporting i of w_i`, separating *how much index* is
   reporting from *how violent* the reporters are expected to be.

The full control regression includes all three. A slope that does not survive control 2 is
reported as a beta-estimation artefact, not as a finding.

## Secondary analyses declared in advance

- **Bellwether windows.** Windows in the top quintile of reporter weight share, reported
  separately with their own N.
- **Sub-periods.** 2010-2016 and 2017-2024, both reported whatever they show.
- **3-day tiling**, as above.

None of these may change the verdict.

## Inference

Bootstrap, 5,000 draws, seed 0, resampling whole **calendar quarters** and refitting the
slope inside each draw. Windows within an earnings season are dependent, and the residual
covariance series is strongly heteroskedastic in exactly the periods the load is high, so
an independent-window interval would overstate precision.

Reported alongside: the plain heteroskedasticity-robust interval, purely so the gap between
the two is visible.

## Decision rule, declared in advance

The mechanism is called **present** only if all three hold:

1. `b > 0` and the quarter-clustered 95% interval on `b` excludes zero on the pooled
   2010-2024 sample under the 5-day tiling.
2. The sign of `b` is the same in **both** sub-periods.
3. `b` remains positive and its quarter-clustered interval still excludes zero in the full
   control regression, and in particular after the market-variance control.

Anything short of all three **kills the covariance strategy at the physical stage**. No
index or ETF option data is acquired, and the QQQ-versus-SPY relative-variance
implementation is not built.

## Declared in advance as non-decisive

The R-squared; the 3-day tiling; the bellwether subset; either sub-period on its own; and
the economic size of `b`, which is a question that only becomes meaningful if the sign and
the interval survive first.

## Known hazards

Announcement dates before roughly 2000 carry a default session label, which is why the
sample starts in 2010. Market capitalisation from CRSP price times shares outstanding does
not adjust for float, so the weights are cap weights and not index weights; the difference
matters for magnitude and not for the sign under test.

The load and the realised covariance are both mechanically larger in earnings season, so
the pooled regression contains a strong seasonal common component. Control 1 exists
precisely for that, and the sub-period and clustered inference are there because a seasonal
regressor with a seasonal outcome is the classic way to manufacture a t-statistic.

## Trial accounting

One trial. Charged to the deflation count whatever the outcome.
