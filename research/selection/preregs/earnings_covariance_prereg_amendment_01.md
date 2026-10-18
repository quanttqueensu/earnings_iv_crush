# Amendment 01 to the earnings-covariance pre-registration

Dated 2026-08-11. The original pre-registration is preserved unmodified; its SHA-256
remains `e3e3f78f0d27e26c45f9f98efb29b5be3d7f0004f64df3ae1d7b13b1857b8852` and must be
verified byte-identical when this run is reported.

The original specification was run once, in full, and its output is retained. It returned a
slope of the sign **opposite** to the hypothesis, strongly and everywhere: pooled
`b = -0.7285`, quarter-clustered interval `[-0.9707, -0.5363]`, same sign in both
sub-periods, both tilings, the bellwether subset, and under every declared control.

That result is **not reported as a finding**, because the estimator is arithmetically
degenerate. This amendment records the defect, the evidence for it, and the corrected
construction, and declares the corrected run as a **second trial**.

## The defect

The original outcome was the cross term of a portfolio of **market-model residuals**,

    C_d = ( sum_i w_i r_perp_id )^2 - sum_i w_i^2 r_perp_id^2,

with `w` the cap weights of the top 500 names and `r_perp` the residual from a regression
of each name on the market factor.

The cap-weighted top 500 *is*, to a close approximation, the market factor. Cap-weighting
residuals taken against that factor therefore produces a portfolio that is approximately
zero by construction, and the cross term collapses to minus the own-variance term.

**Measured, not asserted.** The daily residual portfolio has a standard deviation of
0.001207 against 0.016900 for a typical single name, a factor of fourteen. Its mean squared
value is 1.458e-06 against a mean own-variance term of 1.574e-06, a ratio of 0.926, so the
two quantities being differenced are near-identical in size. Regressing each piece on the
load separately:

| Regressand | Slope on EIL | Correlation |
|---|---|---|
| `own` = sum w_i^2 r_i^2 | +0.9587 | +0.4745 |
| `R^2` = residual portfolio variance | +0.2302 | +0.0593 |
| `C = R^2 - own` (the reported outcome) | **-0.7285** | -0.2120 |

The reported slope is the exact difference of the other two. The load predicts individual
event variance well, which is what it is built to do and is a sanity check passing; it
barely predicts the residual portfolio's variance, because that portfolio is near-degenerate;
and the subtraction turns the first fact into an apparent covariance finding.

The defect is identifiable **a priori** and without reference to the outcome: it is a
property of the estimator, provable from the fact that the residualising factor and the
aggregation weights describe the same portfolio. It was not identified because the original
specification took one of the two constructions the source memo offered without checking
which one the weights made degenerate. That is a specification error, not an unfavourable
result, which is why it is corrected rather than reported.

## Change 1: the covariance is measured on excess returns, not residuals

`x_it = r_it - rf_t`. No market-model residualisation anywhere in the outcome. The window's
per-name realised variance is `v_i = sum over d in t of x_id^2`; the index's is
`V_t = sum over d in t of R_d^2` with `R_d = sum_i w_i x_id`.

The expected event variance is recomputed in the same return space: `J_hat` becomes the
causal expanding mean of the name's prior squared day-0 **excess** returns, minimum four
priors, otherwise unchanged.

## Change 2: the outcome is realised correlation, not the raw cross term

    rho_t = ( V_t - sum_i w_i^2 v_i ) / ( ( sum_i w_i sqrt(v_i) )^2 - sum_i w_i^2 v_i )

This is the standard dispersion-desk correlation measure, applied to realised rather than
implied variances: index variance net of the weighted sum of constituent variances, divided
by what that quantity would be at a correlation of one.

**Why.** On excess returns the raw cross term is dominated by the market factor: weighted
own variance is roughly 1.5% of index variance, so `V - sum w^2 v` is essentially index
variance, and a regression of it on the earnings load would be answering whether earnings
season is a high-volatility period. It is, and that is not the hypothesis. Dividing through
makes the outcome scale-free and asks the actual question: do names co-move more or less
than usual **given** how volatile they individually are.

## Change 3: the test is two-sided, and both signs are interpreted in advance

The source hypothesis predicts `b > 0`: clustered, economically linked announcements create
common information and raise co-movement.

The opposing reading, which practitioner commentary on dispersion trading supports and
which is stated here **before** the run so it cannot be adopted after the fact, predicts
`b < 0`: earnings are firm-specific information events, names move on their own news, and
index correlation falls during earnings season. Note that this direction, if found, is
**already priced** rather than a mispricing. Implied correlation is observed to fall as
earnings get under way and the long-dispersion trade is a standard, crowded expression of
exactly this. A confirmed negative slope is therefore a validated mechanism with no
implied edge attached to it, and the option-stage test would have to establish that the
market moves implied correlation by the *wrong amount*, not merely in the wrong direction.

Sources for that reading are practitioner rather than peer-reviewed and are labelled as
such; no academic confirmation of the earnings-season correlation effect was located, and
a targeted search returned work on idiosyncratic volatility and the announcement premium
rather than on index correlation.

## Change 4: a scale-free load is reported alongside

`EIL` is in variance units and drifts with the volatility level over fifteen years. The
within-sample rank of `EIL` is reported as a secondary regressor. Declared here so it
cannot be promoted to primary afterwards. The primary regressor remains `EIL` itself.

## Unchanged

Universe, prior-year-end cap weights, sample 2010-2024, minimum four priors, the 5-day
primary and 3-day secondary tilings, all three controls, the bellwether and sub-period
secondaries, 5,000 draws, seed 0, quarter-clustered inference as primary with the
heteroskedasticity-robust interval alongside.

## Decision rule, amended for the two-sided test

The mechanism is called **present** only if all three hold:

1. The quarter-clustered 95% interval on `b` excludes zero on the pooled 2010-2024 sample
   under the 5-day tiling. The sign is recorded, not required.
2. The sign of `b` is the same in both sub-periods.
3. The interval still excludes zero with the same sign in the full control regression, and
   in particular after the market-variance control.

If the mechanism is present with a **negative** sign, that is a confirmed physical effect
whose option-market expression is already a crowded trade, and the correct next step is a
pricing test rather than an implementation. If present with a **positive** sign, the source
memo's hypothesis stands and the relative-variance implementation becomes the next step.
If absent, the direction is killed at the physical stage.

## Trial accounting

The defective run is **not** charged as a trial, because its output is discarded and no
inference is drawn from it in either direction. This corrected run is charged as one trial.
The original file and this amendment are reported together so the discard is auditable.

## Binding

No further specification change after this file is hashed. Any further change requires
amendment 02 and all three files are reported alongside the result.
