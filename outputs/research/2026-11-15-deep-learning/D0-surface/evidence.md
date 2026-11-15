# D0 evidence: targets, the L4 benchmark on H_net, and the 15:59 surface tensor

Lane D0 builds the inputs D1 and D2 read and re-runs the benchmark they must beat. All data are
real: L1's corrected panel, L2's hedge commission, the lane E panel, FRED DFF and the cached
Databento 15:59 chains. No pull was made and no network call was made. Every result here is
exploratory: 2019-24 had been viewed before for `H_corr`, and `H_net` differs from it only by a
cost. Basis, unless stated: per trade, % of m0, net at the touch, not annualised; intervals are
date-clustered 95% on announcement dates (`protocol.date_clustered_ci`, 5,000 draws, seed 0).

## Scope and success criteria

D0 has no hypothesis of its own. Its criteria are mechanical: the targets reproduce the team
lead's 2019-24 means, the benchmark re-run reproduces L4's stored run before it is re-pointed at
`H_net`, the surface's front ATM quantities reconcile to the lane E panel within stated
tolerances, five events check by hand against the raw files, and both attrition sources are
tested for outcome dependence.

## Targets (`targets.parquet`, `step1_targets.log`, `step1_results.json`)

Funnel: 9,350 events; `h_status` ok 9,315; `comm_1c` present 9,315; `H_net` defined 9,315; 35
dropped, none filled. The 2019-24 means of `H_corr` and `comm_1c` are -0.011941 and 0.001398
(fractions of m0), as the team lead checked; `H_net` is -1.334% of m0 on 2019-24, -1.203% on
2013-18 and -0.020% on 2025-26 (point means, N 5,113, 2,640 and 1,562).

The 35 events without commission are exactly the 35 `h_status not_reproduced` events, all in
2025-26 and all on the Yahoo stock path, so they have no `H_corr` and the brief's test "in
`H_corr`" cannot be run. Trial 3,134 tests the outcomes they do carry against the other 1,562
events of 2025-26. Stored `H`: -2.05 against -0.05, difference -2.00 [-5.18, +0.36], Welch p
0.24, N=35, so no detectable dependence, though the test is weak at this N. `residual_value`:
-11.61 against -5.54, difference -6.07 [-7.41, -4.47], Welch p 3e-7. The drops are therefore not
outcome-neutral on residual value; the bias reaches only 2025-26, which the brief reads as
exploratory, and it should be stated beside any 2025-26 residual-value figure.

Mechanism: the drops are events whose rebuilt Yahoo stock path did not reproduce the stored `H`
within L1's tolerance; `build_base.py` names a dividend missing from the cached series as the
usual cause, which was not verified event by event here. That is a data-source failure, not a
trading filter, but it falls on names (repeat reporters such as OTIS, CHD and ETR) with worse
residual value, so dropping them flatters a 2025-26 residual-value book slightly.

Name collision: `base_corrected.parquet` has a column `H_net` that is L1's netting correction of
`H`. It is a different quantity, and `targets.parquet` does not carry it.

## The L4 benchmark on H_net (trials 3,132 and 3,133; `step2_benchmark.log`, `step2_results.json`)

The frozen champion and baseline were run through L4's own design (`l4iter.Design`, imported).
The re-run on `H_corr` first reproduced L4's stored `run_H_corr.parquet` log scores with a
maximum gap of 0 nats, so the pipeline is L4's. On `H_net`:

| Block | Model minus baseline, nats per event | N | Clusters | Years positive |
|---|---|---|---|---|
| 2013-18 (descriptive) | +0.0144 [+0.0075, +0.0214] | 2,159 | 595 | 5 of 5 |
| 2019-24 (trial 3,132) | +0.0149 [+0.0088, +0.0207] | 5,113 | 872 | 6 of 6 |
| 2025-26 (trial 3,133) | +0.0240 [+0.0140, +0.0343] | 1,562 | 232 | 2 of 2 |

On `H_corr` the slate-tests figure was +0.0139 [+0.0080, +0.0195], N=5,113. The 2019-24 by-year
gains on `H_net` are +0.0212, +0.0245, +0.0111, +0.0245, +0.0061 and +0.0074 (2019 to 2024).
Model 90% coverage is 0.890 [0.881, 0.900] on 2019-24. The log score is a log density per unit
of % of m0; the difference is unit-free. The hyperparameters were chosen on `H_corr` and not
re-searched for `H_net`, which, if anything, handicaps the benchmark.

Mechanism: the gain on `H_net` is slightly larger than on `H_corr`. A plausible reading
(conjecture, not decomposed here) is that the commission, a fixed per-share cost, is largest
relative to m0 on low-premium names, which the half-spread and implied-move features already
identify, so netting it adds predictable variation that the features explain and the baseline
does not. The model's predictive mean of `H_net` is infinite (Student-t errors on the
Yeo-Johnson power-0 loss ratio), so this benchmark competes on the log score only and cannot
drive the economic rule; `l4_inputs.parquet` supplies the median and P(H_net > 0) instead.

## The surface module and tests

`earnings_iv_crush/research/chain_surface.py` (numpy and pandas only; the normal CDF is
`math.erfc` elementwise) with `ChainSurfaceConfig` and `CHAIN_SURFACE` appended to
`config.py`. Snapshot: the last row per contract stamped at or before 15:59 ET on the entry
date; every chain file holds exactly one row per contract stamped 15:59:00 ET, the pull window
of `research/chains.py`, so the build dropped 0 rows after the cutoff and superseded 0. OCC
parsing reproduces `_parse_chain` (that module loads `.env` at import and is not imported).
`tests/research/test_chain_surface.py` (71 cases, synthetic, offline) checks the inverter
against planted vols and against `hedged_hold.option_iv` on a 300-option random grid (agreement
below 1e-6), exact interpolation of a flat smile, the exclusion of quotes after 15:59, masking
of missing strikes and of a missing expiry, no mid IV from a one-sided quote, and parity
recovery of a planted forward at zero and 5% rates.

One choice goes beyond the lane text: a channel is not interpolated across a bracket wider than
1.0 in x (two grid steps). Without this rule mean fill would be 0.721, 0.840 and 0.809 by block
instead of 0.648, 0.807 and 0.764; the rule costs 2013-18 most, where strikes are coarse in
standardised units.

## The build and checks (`build_surfaces.log`, `check_surfaces.log`, `check_surfaces.json`)

Funnel: 9,350 events; file present 9,350; front expiry found 9,350; next expiry found 9,225;
both 9,225; all-mask 214 (164 in 2013-18); sparse (fill below 0.5) 972. The next forward used
fewer than five parity pairs on 360 events. Fill by point is highest at the money (0.92 front,
0.97 next at x = 0) and lowest at x = +2 (0.30 and 0.26).

Reconciliation on all 9,350 front surfaces: the ATM strike equals the base strike on 9,350; the
ATM straddle half-spread equals the panel's `half_spread` to 3.3e-16 (tolerance 1e-9); the ATM
straddle IV under the panel's convention (zero rate, whole calendar days) equals `front_iv` to
2.5e-9; under the surface's own convention (DFF discount, minute clock) it is within 0.0022 of
`front_iv` on every event, median 0.00013 (tolerance 0.005). Five spot checks, recomputed on an
independent path (regex parsing, `hedged_hold.option_iv` and `straddle_iv` on the discounted
forward), match the stored sigma_atm to 1e-11 and the call and put IV at x = 0 to the float32
rounding of the stored grid (`check_surfaces.json`).

Attrition (trial 3,135). On 2013-24, sparse surfaces have `H_net` -2.84 against -1.10,
difference -1.74 [-2.57, -0.94], N=831 against 6,922, Welch p under 0.001; the difference holds
in 2013-18 (-1.01 [-2.00, -0.04]) and 2019-24 (-3.16 [-4.55, -1.78]), and on `residual_value`
(-0.86 [-1.35, -0.40] on 2013-24). Sparsity depends on the outcome, so no lane may drop sparse
surfaces silently.

Mechanism (`describe_sparse.log`, entry-time quantities only): sparse surfaces are the
illiquid, long-tenor, low-premium events. Their median ATM straddle half-spread is 8.8% of mid
against 4.2%, the median front expiry 15 days against 4, the median ATM standard deviation
0.053 against 0.066, and the premium 16.4% of m0 against 20.0%; Spearman correlation of fill
with half-spread is -0.52. These are the three features that carry L4's forecast (half-spread,
implied move, tenor), so a network that learns "sparse is bad" is relearning the known spread
and tenor effect, and the mechanism check should treat the mask channel with the spread and size
channels.

## Process

`diagnosis.log` records one re-run: black reformatted three scripts after their first runs, so
steps 1, 2 and the build were re-run from the final files; `blocks_viewed.csv` therefore holds
the step 1 and 2 views twice and the second set is the run of record. Output hashes were
unchanged. `scripts_sha256.txt` hashes every script and the module as run.
