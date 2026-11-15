# Deep learning on the 15:59 chain, 2026-11-15: summary

The programme asked whether the full 15:59 option chain forecasts the hedged short-straddle
outcome better than the L4 sequential Bayesian model. The rules are in `BRIEF.md` and `LANES.md`,
and trial numbers were reserved in `RESERVED_TRIAL_IDS.md` before any lane started. There were
three lanes and an independent review:

- D0 built the targets net of commission, re-ran L4 on them as the benchmark, and turned every
  event's chain into a fixed grid;
- D1 built a network that reads the grid;
- D2 was a control network on L4's own features;
- the review (`review/REVIEW.md`) checked the files, not the conclusions.

Everything is exploratory and on real data:

- **Data:** CRSP, the cached Databento chains and FRED. No paid pull was made.
- **Freezes:** they hash themselves and their scorers, and all hashes reproduce, but they were
  not filed as pre-registrations.
- **Blocks:** 2019-24 had been viewed for this outcome family before.

**Basis, unless a row says otherwise.**

- Log scores are the per-event log predictive density of `H_net`, in nats per unit of % of m0,
  with the Jacobian included.
- `H_net` is `H_corr` minus the one-contract hedge commission.
- Book figures are per trade, in % of m0, net at the touch, not annualised.
- Intervals are date-clustered 95%.
- 2019-24 has N=5,113 events on 872 dates.

## Verdict

The chain carries no information about the outcome beyond what L4 already uses. The deep models
beat L4 only because L4's error scale is wrong by tenor, and a three-parameter fix to L4 recovers
almost all of their gain. No model's trades beat the tight-spread screen.

- **The surface adds nothing.**
  - Each surface network scores slightly below its twin without the surface.
  - Blanking the IV, spread, size or mask channels moves the score by at most 0.001.
  - A control given only the two grid fill rates does as well as the full grid.
- **The gain over L4 is per-event scale.** L4 gives every event almost the same predictive scale
  (sd over mean 0.004 to 0.017 by year). Its standardised errors run too wide on short tenors
  and too narrow on long ones.
  - Rescaling L4's predictive by one factor per tenor tercile, fitted causally, gains +0.048 of
    the networks' +0.051 to +0.059. The factors are about 1.24, 0.93 and 0.72, stable across
    quarters.
- **The money fails.** Every rule's selection overlaps the tight-spread-per-date screen on 80 to
  84% of its events, and none beats the screen.

## The forecast, 2019-24

| Model | Trial | Gain over L4 | Gain over L4 rescaled by tenor |
|---|---|---|---|
| L4's no-feature baseline (L4 over baseline is +0.0149 [+0.0088, +0.0207]) | 3,132 | -0.0149 | |
| L4 rescaled by tenor tercile (review check) | 3,212 | +0.0482 [+0.0386, +0.0574] | 0 |
| D1b, surface network boosting L4 (primary) | 3,142 | +0.0512 [+0.0398, +0.0617] | +0.0030 [-0.0029, +0.0085] |
| D1b's twin without the surface | 3,148 | +0.0554 [+0.0446, +0.0661] | +0.0072 [+0.0007, +0.0139] |
| D1a, surface network (secondary) | 3,145 | +0.0556 [+0.0447, +0.0659] | not computed |
| D1b with only the two fill rates | 3,166 | +0.0530 [+0.0419, +0.0638] | not computed |
| D2, tabular network on L4's features | 3,182 | +0.0593 [+0.0498, +0.0684] | +0.0110 [+0.0052, +0.0168] |

- **Years.** Every network gain over L4 is positive in all 6 years, with 2019 and 2020 the weakest.
- **The surface's own contribution.** Surface network minus twin is -0.0042 [-0.0103, +0.0012]
  for D1b and -0.0020 [-0.0077, +0.0037] for D1a. D1b minus the fill-rate control is -0.0018
  [-0.0076, +0.0037].
- **D1 against D2.** D1b minus D2 is -0.0080 [-0.0146, -0.0021] on identical events.
- **Staleness.** The networks refit at each quarter start, while L4 updates after every expiry.
  That asymmetry works against the networks, and their gain does not fade within a quarter.
- **Burn-in.** The gain is not L4's prior or burn-in. At least 2,435 events had settled before
  any 2019 entry, and L4's predictive degrees of freedom are about 1,000 to 1,800.
- **Seeds.** Seed dispersion is 0.001 to 0.002 nats.
- **Robustness.** On 2025-26 (exploratory, N=1,562) every network gains +0.058 to +0.069 over L4,
  and the surface again adds nothing.

**What remains beyond the tenor fix.** D2 keeps +0.011 [+0.005, +0.017] after the tenor rescale,
from a scale that also moves with the half-spread. Occlusion costs it -0.029 [-0.046, -0.016]
for the half-spread and -0.043 [-0.050, -0.035] for tenor. This residual is small, comes from a
model chosen after a 24-configuration search, and needs no network: a linear location and log-scale
model on L4's features (D2's c21, `D2-tabular/search_log.csv`) gave +0.043 of D2's +0.046 on the
development folds.

## The money, 2019-24

The rule is to trade if the predictive mean of `H_net` is above zero. The mean comes from
deterministic quadrature on heads with Gaussian tails in the transformed space. The unconditional
book is -1.33 [-1.73, -0.93].

| Rule | Trials | Selected | Selected mean, `H_net` | Minus tight-spread screen, `H_net` | Minus screen, `residual_value` | Overlap with screen |
|---|---|---|---|---|---|---|
| D1b | 3,143-3,144 | 1,282 | +0.02 [-0.92, +0.91] | +0.11 [-0.38, +0.60] | -0.15 [-0.36, +0.04] | 82.6% |
| D1a | 3,146-3,147 | 1,316 | -0.16 | +0.01 [-0.46, +0.48] | -0.39 [-0.60, -0.19] | |
| D2 | 3,184-3,185 | 1,215 | +0.03 [-0.91, +0.91] | +0.03 [-0.52, +0.58] | -0.04 [-0.26, +0.16] | 80% |
| Fill-rate control | 3,166 | 1,253 | | -0.43 [-1.05, +0.16] | | |

- **Against the matched null.** Every rule beats the matched random null (percentile 100) and the
  unconditional book. The tight-spread screen does as well.
- **2025-26 (exploratory).** D1b minus the screen is +0.32 [-0.65, +1.30], and D2 minus the screen
  is +0.18 [-0.80, +1.10] on `H_net`.
- **The reading.** The trades a density model calls positive are the tight-spread trades. That is
  the spread gate already closed in `docs/RESEARCH_STATE.md`, reached through a predictive mean.

## Other results

- **Benchmark on `H_net`.** L4 re-run on `H_net` beats its baseline by +0.0149 [+0.0088, +0.0207]
  on 2019-24 and +0.0240 [+0.0140, +0.0343] on 2025-26 (trials 3,132 and 3,133). It reproduces
  L4's stored `H_corr` run exactly. `H_net` per trade is -1.20% of m0 on 2013-18, -1.33% on
  2019-24 and -0.02% on 2025-26.
- **Sparse surfaces are worse events (trial 3,135).** Grid fill below 0.5 costs -1.74
  [-2.57, -0.94] % of m0 on 2013-24 (N=831 against 6,922). These are the wide-spread,
  long-tenor, low-premium events. No event was dropped on surface grounds.
- **Commission attrition (trial 3,134).** The 35 events without a commission row are all
  `h_status not_reproduced` in 2025-26, so they have no `H_corr` to test. On `residual_value`
  they are worse events: -6.07 [-7.41, -4.47].
- **L4's infinite mean is a far-tail property.** Truncated at 100 to 10,000 times the premium,
  its mean for the review's test event is -1.08. L4 could be scored on the mean rule with a stated
  loss cap.

## Review corrections

These come from the independent review. The lanes' own files are left as written.

1. **Claim.** Read the forecaster passes (trials 3,142, 3,145 and 3,182) as "L4's error scale is
   wrong by tenor; a network adds at most about 0.01 nats beyond a three-parameter fix". Do not
   read them as a deep-learning result.
2. **Labels.** D2's `trials.csv` rows 3,182 and 3,183 say "pass" with no exploratory label. Row
   3,187 says "pass" on 2025-26, where the forecaster criterion is not defined.
3. **Untraced numbers.** D2's development mechanism numbers trace to no output or script: scale
   sd over mean 0.056, RMS standardised residual 1.25, 0.93 and 0.75 by tenor, and 1.09, 0.96 and
   0.95 by implied move. They are not cited here. The review's file
   `review/check_gain_source.json` holds the traceable version of the tenor finding.
4. **Process.**
   - D2's `units_check.py` was saved 9 seconds after its log and not re-run.
   - D2's diagnosis entry 6 and both `STATE.md` files carry typed times, not clock times.
   - D1's fill-rate control is a 41st development configuration, logged outside `search_log.csv`.
   - D1's search log marks the no-surface controls as eligible, although selection followed the
     declared rule.
   - D1's addendum (trials 3,166 to 3,169) passes both checks: its freeze predates its reads, and
     it edits no frozen module. Its `fill_control` rows in `cards.parquet` carry no flag saying
     they are exploratory and were added after the held-out read; treat them as such.
5. **Minor bias.** D0 uses same-day FRED DFF, which is published the next day. The effect on
   surface IVs is negligible.
6. **New failure class.** A flexible model's gain over a benchmark was credited to its
   architecture or inputs, when the benchmark's own misspecified scale carried it. The check is
   to fix the benchmark's obvious misspecification first and measure the flexible model against
   that.

## Trial accounting

| Source | Trials | Numbers |
|---|---|---|
| D0 | 4 | 3,132 to 3,135 |
| D1 | 28 | 3,142 to 3,169 (3,170 to 3,181 unused) |
| D2 | 8 | 3,182 to 3,189 (3,190 to 3,211 unused) |
| Team lead | 1 | 3,212, the review's tenor-rescaled L4, charged because it is quoted |
| **Total** | **41** | |

For deflation, D1's search is 41 development configurations and D2's is 24. `ledger_entries.py`
appends one `exploratory-unhashed` row per lane to `research/ledger/trials.csv`, plus every lane's
block views to `blocks.csv`. Next free trial number: 3,232.

## What is left

- **L4's likelihood.** L4 should get a variance that depends on tenor, and perhaps on the
  half-spread. The package already has a `variance_weight` option, and the champion runs it at
  "none". This is a forecasting fix worth about 0.05 nats per event. Judged by everything above, it
  will not change the book.
- **Deep learning on this panel is closed for the outcome forecast.** The surface carries no
  incremental information, and the networks' gain is a misspecified benchmark scale.
- **The book's problem is unchanged.** The corrected unconditional book loses about 1.2 to 1.3%
  of m0 per trade net on 2013-24, and every selector found so far reduces to the spread screen.
