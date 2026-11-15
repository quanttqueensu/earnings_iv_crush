# D2, tabular control: evidence

All data are real unless labelled synthetic. The 2019-24 block had been viewed before by L4 and
D0 for this outcome family, so every held-out number here is exploratory in the project's sense,
although D2 itself read it once, after its freeze. 2025-26 is exploratory twice over.

## Hypothesis, scope and success criteria

**Question.** Does a flexible mixture-density network fed only L4's seven 15:59 features and
L4's causal name effect beat the L4 sequential Bayesian champion on the log predictive density of
`H_net`? If it does, a gain of the surface network D1 over L4 may be flexibility rather than
information in the chain.

**Scope.** Target `H_net = H_corr - comm_1c` from D0's `targets.parquet`, in % of m0 per trade,
net at the touch, not annualised. Inputs are the seven declared features exactly as
`l4lib.design` builds them (imported), plus `m_name_effect_at_entry` from D0's
`l4_inputs.parquet`, each standardised on the training rows of each fit. No surface.

**Success criteria** (BRIEF.md, declared in `diagnosis.log` entry [1] before any fit).
Forecaster pass: the 2019-24 mean per-event log-score gain over the L4 champion has a
date-clustered 95% interval above zero and is positive in at least 4 of 6 years. Economic pass:
the rule "trade if the quadrature predictive mean of `H_net` is above 0" beats the
tight-spread-per-date screen (selected minus screen, interval above zero) and the matched random
null (percentile at least 95), on `H_net` and on `residual_value`.

**Basis throughout.** Log scores are nats per event, the log density of `H_net` in % of m0 with
the Yeo-Johnson Jacobian, the same basis as D0's `l4_scores.parquet` (checked: a Student-t in z
with D0's predictive parameters reproduces D0's stored champion score, -3.6750 against -3.6741 on
2,159 development events). Book means are % of m0 per trade, net at the touch, not annualised.
Intervals are date-clustered 95% (announcement-date clusters, 5,000 draws, seed 0).

## Design

- **Model.** z = yj(-H_net / U, 0), the champion's transform, with U the 15:59 premium in % of
  m0. An MLP maps the 8 inputs to a Gaussian mixture in standardised z (K = 1 to 3) or, for the
  log score only, a Student-t. Every head has an input-dependent location and scale.
- **Mean.** Gauss-Legendre quadrature on each side of the branch point z = 0, 128 nodes, tested
  against adaptive integration and two closed forms (`tests/research/test_dl_tabular.py`).
- **Fits.** Early stopping on the last calendar year of each training window, then a refit on
  the full window for the selected number of epochs. Development: rolling origin 2016, 2017,
  2018, training on expiry before 1 January. Held-out: a refit at every quarter start, training
  on expiry before it. Every training row's expiry precedes its origin, asserted in code.
- **Comparators.** The unconditional book; the tight-spread-per-date screen, taking on each
  entry date as many events as the rule takes, those with the smallest 15:59 half-spread. L4's
  `decompose_selection.py` holds only a tercile and a median spread gate, so the screen is
  reproduced from the slate-tests review's description. Also `protocol.matched_random_null`.

## Development (2016-18, 2-seed ensembles)

24 configurations, the full budget (`search_log.csv`). All 24 were re-run with the final code and
reproduce every fold score exactly (`search_log_verify.csv`). Scored events N=1,397 (381, 529
and 487 by fold).

| Configuration | Pooled gain over L4 champion | 2016 | 2017 | 2018 |
|---|---|---|---|---|
| c17 Gaussian K=1, hidden 8 (frozen) | +0.0462 | +0.0492 | +0.0454 | +0.0446 |
| c21 Gaussian K=1, linear location and scale | +0.0433 | +0.0380 | +0.0498 | +0.0404 |
| best K=3 (c10) | +0.0457 | +0.0518 | +0.0433 | +0.0435 |
| best Student-t (c14, frozen secondary) | +0.0376 | +0.0403 | +0.0403 | +0.0326 |
| control c22: flexible location, constant scale | -0.0075 | +0.0071 | -0.0241 | -0.0009 |
| control c23: linear location, constant scale | -0.0042 | +0.0035 | -0.0132 | -0.0004 |
| control c24: c02 without the name effect | +0.0464 | +0.0474 | +0.0456 | +0.0464 |

**What this says.** The development gain is the input-dependent scale and nothing else. A
linear model of the location and log scale captures 94% of it, a flexible network with a constant
scale captures none, extra mixture components add nothing, and L4's name effect adds nothing.
The likely cause is visible in L4's own residuals: its z scale barely varies across events
(sd/mean 0.056), while the root-mean-square standardised residual against L4 falls from 1.25 to
0.93 to 0.75 across terciles of log tenor. L4's likelihood is homoscedastic in its features; a
network that lets the scale depend on the same features scores better.

Development economics (`dev_economics.json`, not a trial): the rule takes 175 of 1,397; selected
minus tight screen +0.98 [-0.33, +2.42] on `H_net`, null percentile 95.3, overlap 77%; on
`residual_value` the selection is worse than random (null percentile 2.1).

## Freeze

`freeze_D2.md`, written 16:30:52Z, records the configuration and the sha256 of
`score_heldout.py`, `d2lib.py`, `d2net.py`, `frozen_config.json` and `search_log.csv`, and hashes
itself; the scorer refuses to run otherwise and refuses to repeat a block. The 2019-24 view is
logged at 16:32:00Z and the 2025-26 view at 16:41:15Z. The scorer ran end to end on synthetic
data first (`synthetic_check/`, SYNTHETIC): a planted location and scale effect scored +0.112
[+0.087, +0.137], the rule passed, and occlusion named exactly the planted inputs.

## 2019-24 held-out (trials 3,182 to 3,185)

Funnel: 5,113 predicted, 5,113 with `H_net`, 5,113 scored by L4 champion, baseline and both D2
heads. D2 refits quarterly; L4 updates after every expiry, so D2 carries up to a quarter of
staleness in every comparison below.

| Comparison, identical events | Gain, nats per event | N | Years positive |
|---|---|---|---|
| D2 Gaussian (c17) minus L4 champion (3,182) | +0.0593 [+0.0498, +0.0684] | 5,113 | 6 of 6 |
| D2 Student-t (c14) minus L4 champion (3,183) | +0.0588 [+0.0492, +0.0686] | 5,113 | |
| D2 Gaussian minus L4 baseline | +0.0741 [+0.0635, +0.0848] | 5,113 | |
| L4 champion minus L4 baseline (D0's figure) | +0.0149 [+0.0088, +0.0207] | 5,113 | |
| D2 Gaussian minus D2 Student-t | +0.0005 [-0.0032, +0.0039] | 5,113 | |

By year (D2 minus champion): 2019 +0.042 [-0.005, +0.094], N=437; 2020 +0.017 [-0.007, +0.037],
N=910; 2021 +0.086 [+0.070, +0.101]; 2022 +0.072 [+0.051, +0.093]; 2023 +0.065 [+0.048, +0.083];
2024 +0.062 [+0.041, +0.083]. All six are positive; the 2019 and 2020 intervals include zero.
The five seeds give +0.0570 to +0.0599 (sd 0.0012). The forecaster criterion is met.

**Staleness.** The gain by month of the quarter is +0.068 [+0.056, +0.081], +0.047
[+0.031, +0.062] and +0.056 [+0.027, +0.086] (month 3 N=341): no monotone decay through the
quarter. The asymmetry runs against D2, so it cannot explain the gain.

**Mechanism.** Occlusion (an input set to its training mean, same fitted network): tenor -0.043
[-0.050, -0.035], half-spread -0.029 [-0.046, -0.016], term spread -0.009 [-0.013, -0.005];
implied move, depth, forward and the name effect move the score by less than 0.003, intervals
including zero. Exploratory, after the read (`explore_2019_24.json`): the gain is U-shaped in
tenor (terciles +0.061, +0.013, +0.104) and L4's heteroscedasticity persists out of sample
(standardised residual RMS 1.28, 1.02, 0.74 by tenor tercile). The held-out gain is the
development mechanism: L4 sets one width for every event, too narrow for short-dated trades and
too wide for long-dated ones, and tenor and spread tell the network which is which. That is
flexibility in the error law on information L4 already has.

**Economics.** The rule takes 1,215 of 5,113.

| Book, % of m0 per trade | `H_net` | `residual_value` |
|---|---|---|
| Unconditional | -1.33 [-1.73, -0.93] | -5.55 [-5.84, -5.26] |
| Selected (3,184 and 3,185) | +0.03 [-0.91, +0.91] | -3.92 [-4.31, -3.56] |
| Tight-spread screen, same per-date count | -0.01 [-0.82, +0.79] | -3.88 [-4.22, -3.56] |
| Selected minus screen | +0.03 [-0.52, +0.58] | -0.04 [-0.26, +0.16] |
| Matched-null percentile | 100 | 100 |

Overlap with the screen is 80%. The rule beats random selection and does not beat the screen,
so it fails the declared economic pass on both outcomes. Against the screen, the selected book
gains +0.81 in premium and gives back -0.72 at settlement (exploratory), the two components a
tighter spread moves, and the 245 events the rule takes that the screen does not earn -1.38
[-3.73, +0.81] against -1.55 [-3.23, +0.00] for the 245 the screen takes instead. The likely
reading (interpretation, not tested): the predictive mean of a short straddle is dominated by
where the premium is collected, which the spread already ranks, while the density's extra
precision is in the width of the distribution, which a mean-above-zero rule barely uses.

## 2025-26 exploratory (trials 3,186 to 3,189)

Funnel 1,597 predicted, 1,562 with `H_net` (the 35 events without commission), 1,562 scored.
D2 minus L4 champion +0.0686 [+0.0552, +0.0816], N=1,562 (2025 +0.071, 2026 +0.066, both
intervals above zero); Student-t +0.0686 [+0.0535, +0.0826]; L4 champion minus baseline +0.0240.
Occlusion again puts tenor (-0.038) and half-spread (-0.022) first. The rule takes 358: selected
`H_net` +2.02 [+0.33, +3.73] against the screen's +1.84 [+0.26, +3.40], selected minus screen
+0.18 [-0.80, +1.10]; on `residual_value` -0.04 [-0.43, +0.37]; null percentiles 99.98 and 100;
overlap 84%. The same reading as 2019-24: the positive 2025-26 book is the screen's.

## Against D1 (descriptive)

On the identical 5,113 events of 2019-24 (`compare_d1.json`, from D1's frozen
`heldout/cards_primary_2019-24.parquet`; the comparison is planned in LANES.md, but its
statistic was not frozen): D1's frozen primary, which boosts from L4 with a convolution over the
surface, scores +0.0512 [+0.0398, +0.0617] over L4, and D1 minus D2 is -0.0080
[-0.0146, -0.0021]. The table in LANES.md asks which case holds. D2 beats L4, and by more than
D1 does, so D1's gain over L4 is accounted for by flexibility on L4's own features, and the
chain adds nothing measurable beyond them on this statistic. The two predictive means correlate
0.81; the rules select 1,282 and 1,215 events, 967 in common.

## Limitations and what was not verified

- `residual_value` is used as stored (fraction of m0, times 100), as L4 used it; its definition
  was not re-derived here. Its block means (-4.2% on 2016-18, -5.5% on 2019-24 and 2025-26,
  against -1.3% for `H_net` on 2019-24) are taken as given and not reconciled.
- The tight-spread-per-date screen is reproduced from the review's description, not imported,
  because `decompose_selection.py` does not contain it.
- The commission inside `H_net` is IB Tiered pricing, recalled, not verified (D0, L2).
- Occlusion sets an input to its training mean in a network trained with it present; it measures
  reliance, not a refitted ablation. The development controls (c22 to c24) are the refitted
  version and agree.
- The comparison of month-of-quarter gains is descriptive and month 3 holds 341 events.
- Process: the search log's header was aligned after stage 2 added two columns (raw file kept);
  `d2net.py` and `d2lib.py` were edited after the search and the whole search was re-run to an
  exact match before the freeze. One block-ledger gap (2019-24 outcomes used as training rows by
  the 2025-26 read) is recorded by a dated correction row.

## Files

`diagnosis.log`, `STATE.md`, `blocks_viewed.csv`, `trials.csv`, `search_log.csv`,
`search_log_verify.csv`, `search_log_raw_appended.csv`, `stage2_configs.json`,
`frozen_config.json`, `freeze_D2.md`, `dev_economics.json`, `heldout_2019-24.json`,
`heldout_2019-24_events.parquet`, `heldout_2025-26.json`, `heldout_2025-26_events.parquet`,
`explore_2019_24.json`, `compare_d1.json`, scripts `d2lib.py`, `d2net.py`, `search.py`,
`dev_economics.py`, `write_freeze.py`, `score_heldout.py`, `explore_2019_24.py`, `compare_d1.py`,
`write_trials.py`, `smoke_synthetic.py`, and `tests/research/test_dl_tabular.py`.
