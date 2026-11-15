# D1 evidence: surface network on the 15:59 chain

All data are real (D0's targets and surfaces from the cached Databento 15:59 chains, L4's
benchmark re-run by D0). Every held-out number is exploratory: 2019-24 was viewed before for
the hedged-hold outcome family (slate-tests rule 5), and 2025-26 is exploratory by the brief.

**Basis.** Log scores are nats per event, the density of `H_net` per unit of % of m0 with the
Jacobian, the same expression as L4's. Gains are this lane's log score minus L4's frozen
champion (`m_log_score` in D0's `l4_scores.parquet`) on the same events. Book figures are means
per trade in % of m0, net at the touch, not annualised, with per-trade Sharpe beside them.
Intervals are date-clustered 95% on announcement dates (5,000 draws, seed 0).

## Hypothesis, scope and success criteria

The brief's hypothesis: the 15:59 chain carries information about the distribution of the
hedged short-straddle outcome that L4's six hand-built summaries do not. Criteria, from the
brief and `diagnosis.log` entry 1, all declared before any real fit:

1. forecaster pass on 2019-24: gain against L4 with a lower bound above zero and positive in at
   least 4 of 6 years;
2. economic pass, on `H_net` and `residual_value` each: the selected book (trade when the
   quadrature predictive mean of `H_net` is above zero) beats the tight-spread-per-date screen
   and the pool at the lower bound, and the matched random null at the 95th percentile;
3. mechanism: channel occlusion and the overlap with the tight-spread screen.

Two architectures (an MLP on the flattened surface, a 1-D convolution over moneyness) and two
variants were searched: D1a predicts the head from the surface, six scalars and L4's seven
features; D1b predicts zero-initialised offsets to L4's z location and log scale.

## Development search and freeze

40 configurations (`search_log.csv`, 30 declared in round 1 and 10 chosen after it), 2 seeds
each, on the folds 2016, 2017 and 2018 (N 381, 529 and 487; 1,397 pooled). The frozen
configurations, chosen by the rule declared in entry 1:

| Configuration | 2016 | 2017 | 2018 | Pooled |
|---|---|---|---|---|
| primary, D1b conv, 8 channels (r2_02) | +0.0154 | +0.0207 | +0.0465 | +0.0283 |
| secondary, D1a conv, 8 channels, K=1 (r2_07) | +0.0245 | +0.0416 | +0.0440 | +0.0378 |
| comparator, D1b without the surface (r2_00) | +0.0149 | +0.0244 | +0.0476 | +0.0299 |
| comparator, D1a without the surface (r2_01) | +0.0440 | +0.0365 | +0.0409 | +0.0401 |

These are best-of-search figures and biased upwards. Already on development, each no-surface
twin matched or beat its surface version. The twins were therefore frozen as comparators,
before any held-out read (entry 4). Mixtures with K of 2 or 3 and the wider convolutions were
unstable on 2017. The Student-t heads never led. `freeze_D1.md` was written at 16:32 UTC, and
every held-out load is stamped after it in `blocks_viewed.csv`.

## 2019-24: the forecast

Quarterly refits (24), 5-seed ensembles. N 5,113 on 872 dates; no event lacked an L4 score.

| Configuration | Gain against L4 | Years positive | Against L4 baseline | Seed sd | 90% coverage |
|---|---|---|---|---|---|
| primary (trial 3,142) | +0.0512 [+0.0398, +0.0617] | 6 of 6 | +0.0661 [+0.0540, +0.0777] | 0.0023 | 0.895 |
| secondary (3,145) | +0.0556 [+0.0447, +0.0659] | 6 of 6 | +0.0705 [+0.0590, +0.0817] | 0.0017 | 0.898 |
| D1b without the surface (3,148) | +0.0554 [+0.0446, +0.0661] | 6 of 6 | +0.0703 [+0.0582, +0.0826] | 0.0015 | 0.896 |
| D1a without the surface (3,151) | +0.0575 [+0.0462, +0.0686] | 6 of 6 | +0.0724 [+0.0599, +0.0848] | 0.0016 | 0.898 |

On the same events, L4's own model-minus-baseline gain is +0.0149 [+0.0088, +0.0207], which
matches D0's trial 3,132. By year, the primary gains +0.009 (2019) and +0.000 (2020), then
+0.061 to +0.076 from 2021 on, as the training window grows.

Both frozen networks pass criterion 1, and the pass is not the surface's.

- **Surface contribution.** The surface network minus its no-surface twin, same events, is
  -0.0042 [-0.0103, +0.0012] for D1b (positive in 1 of 6 years). For D1a it is
  -0.0020 [-0.0077, +0.0037] (3 of 6). See `surface_contribution_2019-24.json`.
- **Occlusion of the primary.** Zeroing a channel group changes the log score by:
  - IV channels: -0.0003 [-0.0017, +0.0011];
  - spread channels: -0.0009 [-0.0026, +0.0007];
  - size channels: +0.0004 [-0.0017, +0.0026].

  The secondary loses -0.0033 [-0.0060, -0.0006] from the spread channels and nothing from the
  others.

**Mechanism (exploratory, chosen after the read; `explore_gain_primary_2019-24.json`).** The gain
is a scale model, not information from the chain.

- The Gaussian version of L4 (L4's own z location and scale) scores -0.0033
  [-0.0064, -0.0007] against L4, so the head shape alone is worth nothing.
- The network gains +0.0545 [+0.0431, +0.0659] over that Gaussian. It barely moves the
  predictive mean: the mean shift is -0.15 % of m0, with sd 1.32 across events.
- It does move the predictive sd: the log ratio to the Gaussian L4's sd has sd 0.31 across
  events.
- By tercile of that ratio, the gain is +0.086, +0.009 and +0.058. It sits where the network
  narrows or widens L4's interval the most.
- The no-surface twin shows the same pattern: +0.0587 over the Gaussian L4, and terciles
  +0.089, +0.014 and +0.064.

L4's frozen champion uses no variance weight (`variance_weight="none"`). Its z scale is
therefore common to all events, apart from parameter uncertainty. The network learns a
per-event scale from the six scalars (ATM IVs, tenors, forward, m0) and L4's features. This is
"more flexibility" in the brief's sense, in the variance rather than the mean. D2's control,
which has L4's features without these scalars, is the test of whether the scalars matter too.

## 2019-24: the book

The pool is N 5,113. The unconditional book makes -1.334 [-1.731, -0.926] on `H_net` and
-5.547 [-5.839, -5.256] on `residual_value`.

| Configuration, outcome | Selected | Selected mean | Tight screen | Overlap | Selected minus tight | Selected minus pool | Null percentile |
|---|---|---|---|---|---|---|---|
| primary, `H_net` (3,143) | 1,282 | +0.020 [-0.918, +0.910] | -0.089 | 0.826 | +0.109 [-0.380, +0.595] | +1.354 [+0.596, +2.093] | 100.0 |
| primary, `residual_value` (3,144) | 1,282 | -4.013 [-4.401, -3.630] | -3.864 | 0.826 | -0.149 [-0.360, +0.041] | +1.534 [+1.232, +1.837] | 100.0 |
| secondary, `H_net` (3,146) | 1,316 | -0.161 [-1.034, +0.701] | -0.173 | 0.826 | +0.011 [-0.461, +0.478] | +1.173 [+0.478, +1.836] | 100.0 |
| secondary, `residual_value` (3,147) | 1,316 | -4.455 [-4.848, -4.066] | -4.062 | 0.826 | -0.393 [-0.599, -0.190] | +1.093 [+0.796, +1.387] | 100.0 |

Per-trade Sharpe of the selected book on `H_net` is +0.0013 (primary) and -0.0107 (secondary).
Both rules fail criterion 2. The selection beats the pool and the random null by a wide
margin. But 82.6% of it is the tight-spread-per-date screen, and the screen at matched
participation earns the same or more. On `residual_value` the secondary is significantly worse
than the screen.

The mechanism is the closed spread gate again, reached through the predictive mean. The
no-surface comparators (3,149, 3,150, 3,152, 3,153) also fail; their `H_net` books trail the
screen by -0.48 and -0.37.

## 2025-26, exploratory

N 1,562 with an outcome, of 1,597 predicted. The 35 events without commission have no outcome,
and 3 of them were selected by the primary. Gains against L4:

- primary +0.0583 [+0.0444, +0.0717], secondary +0.0667 [+0.0522, +0.0802], positive in both
  years;
- the no-surface twins +0.0642 and +0.0686;
- surface contribution for D1b -0.0059 [-0.0114, -0.0008], for D1a -0.0019 [-0.0076, +0.0035].

Books:

- primary: 314 selected, +2.606 [+0.729, +4.477], against +2.287 for the tight screen (overlap
  0.847); selected minus tight +0.319 [-0.651, +1.296];
- secondary: selected minus tight +0.042 [-0.694, +0.776];
- `residual_value`: -0.222 [-0.675, +0.265] (primary) and -0.143 [-0.491, +0.206] (secondary)
  against the screen.

All fail criterion 2 again. The book's level in 2025-26 is the block's, and the screen captures
it.

## Addendum: fill-rate control and mask occlusion

The team lead requested these after the held-out reads above, so both are exploratory. The
code is `addendum.py`, frozen by hash in `freeze_D1_addendum.md`; it imports the frozen modules
and edits none of them.

**Fill-rate control** (trials 3,166 and 3,167). D1b with the primary's trunk, no grid, and
only `fill_front` and `fill_next` added to L4's seven features.

| | Development, pooled 2016-18 | 2019-24 against L4 | Primary minus control |
|---|---|---|---|
| 2019-24 | +0.0175 (N 1,397) | +0.0530 [+0.0419, +0.0638], 6 of 6 years | -0.0018 [-0.0076, +0.0037], 2 of 6 years |
| 2025-26 | | +0.0653 [+0.0504, +0.0795] | -0.0070 [-0.0128, -0.0012] |

The rule declared in the addendum freeze applies. The primary's gain over L4 is not larger
than the control's, so whatever the chain adds is reported as how sparse the chain is, a
liquidity measure.

The evidence supports a weaker claim than that. Every variant gains between +0.051 and +0.058
over L4: with the grid, with the six scalars only, or with the two fill rates only. Within the
surface networks, zeroing the mask has no effect (below). The gain is therefore carried by the
network's per-event scale on inputs L4 already has. A fill rate is one sufficient input for it,
not a necessary one. D2, with L4's features alone, settles whether any chain-derived input is
needed at all.

The fill control's book fails the same way. On `H_net` it trails the tight-spread screen by
-0.430 [-1.049, +0.156] (1,253 selected, 2019-24).

**Mask occlusion** (trials 3,168 and 3,169). The frozen primary and secondary were refit on
2019-24 with the frozen code. The refit reproduces the stored log scores exactly (maximum gap
0.0 on 5,113 events), which settles the GPU determinism caveat below. Change in log score:

- primary: mask zeroed +0.0001 [-0.0008, +0.0011]; mask at its training mean per point
  -0.0002 [-0.0005, +0.0001];
- secondary: mask zeroed -0.0007 [-0.0029, +0.0015]; mask at its training mean -0.0003
  [-0.0009, +0.0003].

The three original arms reproduce to the fifth decimal.

## Asymmetries and caveats

- **Staleness.** The network refits quarterly while L4 updates after every expiry, which works
  against the network. D1b takes L4's prior predictive location and scale on every row, so only
  its offsets are stale.
- **The no-surface twins keep the six surface scalars.** "No surface" means no grid. It does
  not mean L4's features only.
- **Process.**
  - `search.py` crashed after its first configuration. It was fixed and round 1 restarted from
    zero (entry 2).
  - `explore_gain.py` was re-run after a lint edit, with identical output.
  - `decompose_selection.py` does not hold the tight-spread-per-date screen. It was reproduced
    from the slate-tests SUMMARY text (`d1eval.tight_screen`), with ties broken by the stable
    event order.
- **Determinism.** Determinism is set with `warn_only=True`. The addendum refit reproduced the
  stored 2019-24 log scores exactly.
- **Units and target.** `H_net` is `targets.parquet`'s column. `base_corrected.parquet`'s own
  `H_net` is never read. Log scores are per % of m0, like L4's: the Gaussian version of L4
  scores -0.0033 nats against L4, not about ln 100.
