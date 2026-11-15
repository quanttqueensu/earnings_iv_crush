# What the sequential model learned

Lane L4, iteration round 1 (frozen) and round 2 (exploratory). Every number below is read from
a file in this folder, named beside it. Basis throughout: per trade, `H_corr` in % of m0, net
at the touch, not annualised; log scores in nats per event; intervals are date-clustered 95%
(5,000 draws, seed 0) unless called credible. 2019-24 and 2025-26 were both viewed for this
outcome family before this lane, so every held-out number is exploratory. Real data
throughout; synthetic results live only in the tests and `pipeline_check.log`.

## The model in one paragraph

The champion (`freeze_online_bayes.md`, `config.ONLINE_BAYES_L4_MODEL`) does not model `H_corr`
directly. It models the loss ratio `-H/U`, with `U` the premium sold at the 15:59 bid in % of m0,
through a Yeo-Johnson transform of power 0. For a loss that is the log of the payout ratio, the
seller's natural scale. The error is Student-t with 30 degrees of freedom, as a scale mixture.
On top sit seven declared 15:59 features, a name intercept, no feature forgetting and a variance
discount of 0.99 per update date. The baseline has the same likelihood with only the intercept
and the name. The search tried 800 configurations on 2015-18 (`search_log.csv`; 568 for
`H_corr`, 232 for `residual_value`). The wide 26-feature set, the industry level and feature
forgetting never beat the simpler choices by more than the 1e-4 tie margin. Most of the
improvement came from the likelihood. The best model of `H` itself (row 246, Student-t with 3
degrees of freedom) scored -3.760 nats per event on 2015-18 and put 9.9% of PITs below 0.05 and
0.5% above 0.95. The champion scores -3.699 and puts 5.4% and 4.7% there (`search_log.csv`,
`heldout_results.json`).

## Which features carry weight

Posterior mean and 95% credible interval on the model scale, after the last update of each
period (`insight_numbers.json`, `fig_coef_paths.png`). A positive coefficient means a larger
loss ratio, which is worse for the seller.

| Feature | End 2018 | End 2024 | End of run (2026-08) | Reading |
|---|---|---|---|---|
| intercept | -0.050 [-0.073, -0.026] | -0.034 [-0.048, -0.020] | -0.041 [-0.054, -0.028] | the median trade pays out less than its premium |
| log_half_spread | +0.073 [+0.048, +0.098] | +0.073 [+0.060, +0.085] | +0.066 [+0.055, +0.077] | stable; the spread's cost on the bid |
| log_implied_move | -0.049 [-0.081, -0.017] | -0.039 [-0.059, -0.020] | -0.042 [-0.060, -0.025] | stable; richer events pay out less per unit of premium |
| log1p_dte | +0.085 [+0.045, +0.125] | +0.069 [+0.042, +0.095] | +0.065 [+0.040, +0.089] | stable, drifting down; tenor beyond the event costs the seller |
| iv_term_spread | +0.041 [+0.003, +0.078] | +0.003 [-0.020, +0.027] | -0.009 [-0.030, +0.013] | excluded zero in 2018, near zero by 2024 |
| iv_term_spread_missing | -0.027 [-0.055, +0.002] | -0.009 [-0.024, +0.007] | -0.008 [-0.022, +0.006] | not distinguishable from zero |
| log_depth | +0.010 [-0.014, +0.034] | -0.008 [-0.022, +0.006] | -0.010 [-0.022, +0.003] | not distinguishable from zero |
| log_forward | -0.017 [-0.040, +0.006] | -0.011 [-0.025, +0.003] | -0.009 [-0.021, +0.003] | not distinguishable from zero |

Three features carry the forecast: the half-spread, the implied move and the tenor. Their
intervals exclude zero and their signs agree at all three snapshots. The term spread is the
instructive one. Its coefficient excluded zero at the end of 2018 and had decayed to zero by 2024 (the panel in `fig_coef_paths.png`). That is the path of the
term selector, which passed in-sample and failed out of sample (`docs/RESEARCH_STATE.md`). A
model updated sequentially shows the decay as it happens, not after a year-block refit.

These features are a small part of the variance. On 2019-24 the linear predictor's standard
deviation across events is 0.107 on the model scale (`decomposition.json`). The residual scale
is 0.511 (`gauge_baseline_H_corr.csv`, last row). The features therefore explain about 4% of the
variance of the transformed loss ratio. The name intercepts vary by 0.019, less than any of the
three carrying features.

## Primary result: the density forecast improves out of sample

Model minus baseline, mean per-event log score (`heldout_results.json`, `trials.csv`):

| Block | Difference | N (dates) | By year |
|---|---|---|---|
| 2015-18, discovery, best of the search (3,012) | +0.0143 [+0.0071, +0.0218] | 1,806 (489) | 2015 +0.014, 2016 +0.008, 2017 +0.017, 2018 +0.016 |
| 2019-24 (3,013) | **+0.0139 [+0.0080, +0.0195]** | 5,113 (872) | +0.019, +0.023, +0.010, +0.023, +0.006, +0.007 |
| 2025-26 (3,014) | **+0.0231 [+0.0134, +0.0331]** | 1,562 (232) | 2025 +0.024, 2026 +0.022 |

Both blocks pass the declared rule (lower bound above zero). The 2019-24 gain matches the
discovery gain, so selecting from 800 configurations did not inflate it. The power calculation
on discovery gave a minimum detectable difference of 0.0065 nats for 2019-24, so this test was
well powered. The effect is still small: 0.014 nats per event is a likelihood ratio of about
1.4% per trade. The yearly gain fell in 2023-24 (+0.006 and +0.007), alongside the drift in the
tenor and term-spread coefficients.

Calibration, frozen model (`heldout_results.json`). 2019-24: 90% coverage 0.890 [0.880, 0.900],
PITs below 0.05 5.3% and above 0.95 5.7%. 2025-26: coverage 0.908 [0.893, 0.922], tails 3.8%
and 5.4%. The baseline is as well calibrated (0.893 and 0.904), because the likelihood does the
calibrating and the features sharpen the location. The PIT histograms still reject uniformity
(chi-square p 0.002 and 0.0003, treating events as independent, so descriptive). The
`fig_pit.png` shape in 2025-26 is tilted upwards: outcomes beat the forecast more often than it
expected, which fits the 2025-26 pool mean of +0.09% against about -1.2% in 2019-24.

**Which driver carries the density gain (round 2, exploratory, 2025-26 only, trial 3,022,
`round2_results.json`).** The same frozen model without `log_half_spread` and `log_depth`
gains +0.0213 [+0.0149, +0.0278] over the baseline. The full champion beats it by only +0.0018
[-0.0065, +0.0098]. The density gain therefore comes from the implied move and the tenor, not
from the cost features. It is not the closed spread gate in another form.

## Secondary: the selected book has selection skill and no reliable edge

Declared rules, frozen model, against a date-stratified random null (same count on each date):

| Rule, block | Selected | Mean H_corr | Per-trade Sharpe | Null percentile | Selected minus unselected |
|---|---|---|---|---|---|
| P(H > 0) > 0.5, 2019-24 (3,015) | 3,741 of 5,113 | -0.55 [-1.01, -0.11] | -0.041 [-0.073, -0.008] | 100.0 (null median -1.06) | +2.40 [+1.68, +3.17] |
| E[H] > 0, 2019-24 (3,020) | 1,800 of 5,113 | +0.10 [-0.60, +0.82] | +0.007 [-0.039, +0.057] | 100.0 (null median -0.86) | +2.00 [+1.16, +2.87] |
| P(H > 0) > 0.5, 2025-26 (3,016) | 980 of 1,562 | +1.18 [+0.20, +2.17] | +0.081 [+0.014, +0.155] | 100.0 (null median +0.30) | +2.93 [+1.78, +4.16] |
| E[H] > 0, 2025-26 (3,021) | 496 of 1,562 | +2.38 [+1.05, +3.78] | +0.151 [+0.064, +0.255] | 100.0 (null median +0.62) | +3.36 [+1.86, +4.87] |

The model ranks events well: every book sits at the top of its null. It does not find a book
that earns money in 2019-24, the larger and better-hedged block (CRSP closing quotes). In
2025-26 it does, but that block is Yahoo-hedged with an assumed 3 bp half-spread, has 232
dates, was viewed before, and its pool mean is already positive.

Three readings temper this.

1. **The book's economics come from the spread.** On 2019-24 the selected-minus-unselected
   gap of the P rule, by L1 component, is premium +2.56 and settlement -0.90, with the hedge
   +0.64 (`decomposition.json`). The selected events collect a larger premium share of m0
   and give some of it back at settlement. That is what a tight spread does to the bid. The
   decision correlates -0.60 with the half-spread's contribution. Inside the tightest causal
   half-spread tercile the P rule takes almost everything (1,956 of 1,986).
2. **The closed spread gate does about as well.** Half-spread below its causal median, on the
   same events: 2019-24 mean -0.38 [-0.90, +0.15] (N 2,842), 2025-26 +1.35 [+0.20, +2.47]
   (N 609). It overlaps 71% and 61% with the P rule. Without the cost features (round 2) the
   2025-26 P-rule book (1,195 selected) drops to +0.64 [-0.21, +1.51], still at the 99.2nd
   null percentile. The
   books select different counts, so this comparison is descriptive, not a paired test.
3. **The residual-value check is confounded by tenor.** Selected minus unselected residual
   value is +4.2 to +4.4% of m0 in every held-out book. Residual value is the extrinsic left at exit,
   and the model prefers short tenors (`log1p_dte` +0.065), which mechanically leave less
   extrinsic. Inside half-spread terciles the 2019-24 gap stays at +3.8 to +6.3. This is the tenor
   asymmetry, not separate evidence of skill.

**The expected-value rule rests on a truncated mean.** Under a power-0 transform with a
Student-t error the predictive mean of `H` is minus infinity for every trade. The loss branch is
exponential, and a t tail has no moment generating function. The rule's Monte Carlo mean (2,000
common draws) is therefore a trimmed mean. It ranks events consistently, but it is not an
expectation. Read trials 3,020 and 3,021 as a rule on a trimmed predictive mean.

## The gauge (F4): it never said the book makes money

As declared, the gauge is the baseline intercept's posterior. Under the loss-ratio transform it
reads P(the median trade gains). It sat above 0.5 on all 579 update dates and gave "promote" on
558 of them, the first on 2014-02-18 (`heldout_results.json`, `fig_gauge.png`, top panel). That
is true and economically misleading. The median trade gains while the mean loses, because the
loss tail is long.

Two mean-based readings say the opposite. The event-weighted mean of settled `H_corr` ends at
-0.97% [-1.26, -0.68] with N 9,009 (`gauge_book_mean.csv`, analytic date-clustered interval). It
was above zero only on the first update date, with one trade settled (`fig_gauge.png`, bottom
panel). The round-2 mean monitor reads the frozen baseline's posterior, with the Gaussian
component because the t mean does not exist (`round2_results.json`). It puts P(book mean > 0)
below 3e-12 on every 2025-26 update date, with a model-implied typical-trade mean of -1.36% to
-1.64%. So the answer to "did the book-level gauge ever cross 0.5" is yes for the declared
median gauge, from the start, and no for any mean gauge after the first trade. A monitor for
this book has to be built on the mean.

## What to carry forward

- The density model is a real, small improvement out of sample, carried by the implied move and
  the tenor, with stable signs. It is a better forecaster of the distribution of `H`. It is not
  a source of edge beyond the spread gate.
- The loss-ratio transform is the main modelling lesson. It fixes the calibration of every
  later model of this outcome, and it changes what an intercept or a "mean" gauge means.
- The term-spread path is a compact explanation of why the term selector failed.

Absolute path of this note:
`C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-slate-tests\L4-bayes\insight.md`
