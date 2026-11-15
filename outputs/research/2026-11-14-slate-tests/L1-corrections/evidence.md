# L1 corrections: evidence by idea

A2, A3 and F2 (early assignment, financing, the ex-date skip) and the corrected panel are
documented in `CORRECTIONS.md`. This file covers A5, A1, A6, A4 and A7.

**Basis, unless a section says otherwise.** Per trade, not annualised. Hedged-hold figures are in
% of m0 (0.20 times the 15:59 parity forward plus the 15:59 straddle bid), net at the touch.
Intervals are 95% percentile intervals that resample whole dates (`protocol.date_clustered_ci`,
5,000 draws, seed 0). Every block read here had already been viewed for its outcome family, so
every figure is exploratory. All results are real data.

## A5. Netted strangle; trials 1,819 and 1,826 under `HEDGED_NET`

**Nearest closed work.** Lane B of the 2026-11-13 alpha hunt (`laneB-contract-choice`), which
valued every alternative contract under the unnetted convention, and trial 1,856, which adopted
netting for the straddle only. This re-values the same events and the same frozen statistics; the
only change is the settlement convention, applied to both arms.

**Package.** `hedged_hold.hedged_short_strangle` settles the residual `h - 1[S>Kc] + 1[S<Kp]` under
`HEDGED_NET`. Under `HEDGED` it reproduces the closed smile-strike study's strangle to 1e-13 per
share in tests, and to 1e-12 on all 7,488 real calls. Tests are in
`tests/research/test_hedged_strangle.py`.

**Re-valuation.** `a5_revalue.py` re-runs lane B's builders unedited with the netted valuations.
The netted ATM straddle equals `base_corrected`'s `H_net` on all 7,753 events. The unnetted rerun
reproduces the logged held-out points exactly.

| Trial | Block | Unnetted (logged) | Netted | N |
|---|---|---|---|---|
| 1,819 tight-of-three strike | 2013-18 | +0.099 [+0.011, +0.185] | +0.090 [-0.004, +0.177] (2,832) | 2,550 |
| 1,819 | 2019-24 | +0.209 [+0.138, +0.283] | +0.211 [+0.140, +0.284] (2,833) | 5,092 |
| 1,826 vol-tight strangle vs H | 2013-18 | +0.491 [+0.275, +0.704], t 4.49 | +0.420 [+0.205, +0.631], t 3.86 (2,834) | 2,447 |
| 1,826 | 2019-24 | +0.555 [+0.400, +0.709], t 7.04 | +0.495 [+0.340, +0.649], t 6.28 (2,835) | 5,041 |

The level of the chosen book stays negative. For 1,819 it is -0.62% [-1.07, -0.18] in 2013-18
and -0.83% [-1.23, -0.44] in 2019-24. For 1,826 it is -0.24% [-0.67, +0.19] and -0.51%
[-0.93, -0.10].

**Mechanism.**

- *1,819.* Netting is neutral across strikes. It adds +0.219, +0.220 and +0.211% of m0 at the
  ATM strike and its two neighbours in 2013-18, and about +0.22% at all three in 2019-24. The
  gain of switching strikes therefore stays what lane B decomposed it into: the entry half-spread
  saved (+0.52% of m0 on switched events in 2019-24), less the mid P&L forgone. On discovery the
  netted interval now touches zero. The lever is a cost saving, and it does not depend on how
  the hold settles.
- *1,826.* Netting helps the straddle more than the strangle. A straddle always has one leg in
  the money at expiry, so its assigned share always nets against the hedge. The strangle often
  expires with both legs out of the money, and then there is nothing to net. Vega-matched to H,
  the strangle gains +0.145% [+0.137, +0.153] of m0 from netting in 2013-18 and +0.157%
  [+0.146, +0.171] in 2019-24, against about +0.22% for H. The paired edge shrinks by about 0.07
  points. It still clears the frozen t >= 3 in both blocks, and it is still carried by the richer
  wing premium per unit of vega.

**Wing attrition of 1,826 depends on the outcome.**

- *Where the drops happen.* All drops are at the first step: no IM/2 wing is quoted (193 of
  2,640 events in 2013-18, 72 of 5,113 in 2019-24, plus one hedge-vol failure). The dropped
  events have a smaller implied move (median 4.1% against 4.6% in 2013-18).
- *Their outcomes are worse.* Their `H_net` is lower by -2.14% [-3.73, -0.64] of m0 in 2013-18
  and -3.71% [-6.40, -1.20] in 2019-24. Their residual value is lower by -2.00% [-2.96, -1.16]
  in 2013-18 and -1.16% [-3.08, +0.45] in 2019-24.
- *Link to the move.* The drop rate falls with the realised move relative to the implied move:
  9.1% below half an implied move against 4.6% above two, in 2013-18.
- *What it does to the statistic.* The paired statistic is read only on surviving events, and the
  strangle-minus-straddle gap on the dropped events cannot be observed. If the gap there were
  zero, the block-level effect would dilute to +0.39% (2013-18) and +0.49% (2019-24) of m0. The
  attrition makes 1,826's book level look better than the full universe would, not its paired
  edge.

## A1. The 2025-26 ledger re-struck at the strike nearest the 15:59 parity forward

**Nearest closed work.** The frozen 2025-26 block (`research/frozen_selector/score_oos_2026.py`,
`oos_2026_ledger.csv`). The earnings-adjacent hunt found its strike sat below the forward
because the spot was a dividend-adjusted close. `a1_restrike.py` imports the frozen logic
unedited. It replaces only the spot handed to `_straddle` and to the margin with the front
expiry's 15:59 parity forward from the cached chain.

**Basis.** The frozen scorer's: per-trade net return on Reg-T margin, marked at mids, net of
11.6% of premium round trip, with Sharpe intervals clustered by entry date.

**Strike centring.** Mean ln(F/K) moves from +186 bp [+166, +204] (median +141, N=1,221) to
+2.1 bp [-2.6, +6.7] (median 0, N=1,312).

**Funnel.** 2,037 events. Dropped: 622 with the exit leg unquoted at the sold strike, 41 with the
entry unquoted at the money, 32 with no entry chain, 29 with no parity forward, 1 with no exit
chain. 1,312 scored.

| Arm | Defective ledger | Re-struck |
|---|---|---|
| Unconditional, per-trade Sharpe | +0.043 [-0.026, +0.120], N=1,221 | +0.017 [-0.052, +0.090], N=1,312 (2,836) |
| Term gate q80 | -0.210 [-0.347, -0.058], N=232 | -0.325 [-0.462, -0.186], N=239 (2,837) |
| Matched random gate | +0.105 [-0.030, +0.270], N=224 | +0.096 [-0.030, +0.250], N=245 (2,838) |

**Paired change, on the 1,114 events in both ledgers.**

| Arm | Mean net RoM change | Sharpe change | N |
|---|---|---|---|
| Unconditional | -0.09% [-0.43, +0.24] | -0.008 [-0.040, +0.025] | 1,114 |
| Term gate | -1.01% [-1.91, -0.19] | -0.086 [-0.150, -0.027] | 206 |
| Random gate | -0.22% [-0.94, +0.47] | -0.016 [-0.085, +0.055] | 205 |

**Attrition is not neutral.**

- *Lost events.* 106 events of the old ledger cannot be scored after the re-strike, mostly
  because the forward strike's exit leg is unquoted. Their old net RoM averaged +3.9%, against
  +0.14% on the paired events: a gap of +3.8 points [+1.4, +6.1].
- *Gained events.* The 197 events the re-strike adds are not different: +0.7 [-0.6, +2.1].
- *Reading the change.* Part of the unconditional change is composition, the loss of events the
  old strike happened to mark well. The paired rows are the clean read.

**Mechanism.**

- *Where the old book's sign came from.* A strike below the forward leaves the short straddle net
  short the stock overnight, because the call is in the money. Re-struck minus old correlates
  +0.46 with the signed reaction return: +2.7 points of RoM when the stock rose (548 events),
  -2.8 when it fell (566).
- *The term gate.* The term-gated events fell by 1.59% on average across the reaction. The old
  ledger's accidental short delta was paid on them, so the gate's -0.21 was flattered by a
  directional bet the rule never made. Re-struck, the gate loses -1.11% [-2.02, -0.27] of gross
  RoM on paired events, and its Sharpe falls to -0.33.
- *Cost.* The 11.6%-of-premium cost falls by 0.16 points of margin, because the old in-the-money
  straddle carried intrinsic in its credit.
- *Verdict.* The headline conclusion does not change, but the gate is worse than recorded, and
  the unconditional book is flat.

## A6. The 53aa4898 panel and the 1,779 and 1,780 contract source

**Nearest closed work.** 53aa4898 (`research/execution/2026-11-02-maker-entry-hedged-hold/`):
resting entry at the 15:00 mid, crossing at 15:59:00, combined with the hedged hold on the 2025-26
ledger contracts. Its strike came from the defective ledger: mean ln(F/K) +180 bp
[+160, +199], N=1,136.

**What can be re-struck.**

- *The hold can be re-struck.* `base_corrected`'s 2025-26 strike equals the strike nearest the
  15:59 parity forward on all 1,136 events. `H_net` at that strike exists for 1,126 of them, with
  a mean of +1.12% [+0.23, +1.94] of m0. On the same events, the stored H at the ledger strike is
  +1.61% [+0.67, +2.49].
- *The lever only partly.* The 2025-26 tick files hold only the two ledger contracts. That is
  verified on all 1,136 events. The resting fill can therefore be re-measured only where the
  ledger strike already is the forward strike: 464 events. The other 672 need a new, metered
  tick pull.

**Re-scored lever (P1), same-strike events.** +0.997% [+0.802, +1.200] of m0, N=464 (trial
2,839). The full panel gives +0.890% [+0.767, +1.009], N=1,136. The moved-strike events
gave +0.816%; moved minus same is -0.18 [-0.43, +0.07].

**P2 at the forward strike, netted, on the same-strike events.** The per-trade Sharpe of
`H_net` plus the lever is +0.180 [+0.072, +0.305], N=459 (trial 2,840). `H_net` alone gives
+0.103 [-0.003, +0.220].

**Mechanism.**

- *The lever survives.* It is not an artefact of the off-centre strike. The improvement on
  correctly struck contracts is at least as large as on the moved ones, and both legs fill
  slightly more often there (64% against 58%).
- *What the strike defect did.* It moved the hold, not the lever. H at the ledger strike reads
  about half a point of m0 higher than `H_net` at the forward strike on the same events, the
  short-delta effect seen in A1.
- *The size is still unconfirmed.* The 2023-24 confirmation (1,779) found about a quarter of this
  size on clean contracts, so the 2025-26 size stays unconfirmed. The same-strike subset is also
  selected: these are the events whose dividend adjustment was too small to move the strike.

**Contract source of 1,779 and 1,780.** The contracts are the strike column of the CRSP-era
hedged-event-hold panel (`outputs/research/2026-11-02-hedged-event-hold/events.parquet`, read as
`strike_mkt`). That strike is chosen by `atm_quote` on the 15:59 parity forward. All 1,712 tick
files under `data/cache/flow/broad_2023_2024/` hold exactly that strike, which equals
`base_corrected`'s. Its mean ln(F/K) is +5.4 bp (median +1.4 bp, mean absolute 64 bp, which is
strike spacing), N=1,712. The confirmation is untouched by the defect.

**Defect reach.** `defect_table.csv` lists fifteen panels:

- five can be re-struck from cached chains (calendar cost, final earnings set t1, p5 strangle,
  section 2.1 peer, the summer figures);
- four rest on 2025-26 tick files that hold only the ledger contracts, and need a metered pull
  (the broad 2025-26 tick contracts, lane F's broad exit arm, E1 and E2's signal);
- two are partly re-struck (53aa4898 and the private ml4 E1 book), and the A1 ledger is done;
- three are clean (the 2025-26 hedged-hold confirmation, 1,779 and 1,780, and the 2013-24 CRSP
  and megacap panels).

## A4. Special dividends of USD 12.50 or more per contract inside holds

**Nearest closed work.** E4's ex-dividend audit (earnings-adjacent hunt), which excluded three
specials by hand. The rule being checked is OCC's adjustment (By-Laws Article VI, Section 11A,
recalled and not verified at source). A non-ordinary cash dividend of at least USD 12.50 per
contract reduces the strike by the dividend. An ordinary dividend is never adjusted.

**Counts.** 890 of 9,350 events hold an in-hold dividend of at least USD 0.125 per share: 267 in
2013-18, 499 in 2019-24 and 124 in 2025-26. `build_base`'s classifier flags 6 as non-ordinary:
PGR 2014-01, HLT 2017-05, FANG 2020-05, DRI 2021-06, and FANG 2022-05 and 2022-08. These are
excluded from early exercise in `H_corr`, and their settlement still uses the unadjusted strike.

**Settlement against OCC's rule.** `a4_special_divs.py` assumes every flagged event was
adjusted, which is an upper bound.

- *The size of the bound.* The per-event settlement change ranges from -8.3 to +24.3% of m0.
  It moves the block means by +0.009% (2013-18, 2 events) and -0.003% (2019-24, 4 events) of m0
  per trade. There are none in 2025-26.
- *Which events were adjusted.* By recall, only PGR's January 2014 distribution contained a
  declared special (USD 1.00 inside USD 1.4929). FANG's 2022 variable dividends may have been
  treated as ordinary. The other three look like regular declarations that the irregularity
  ratio flagged; HLT, for example, is flagged after its 2017 reverse split.
- *How to settle it.* Neither OCC's memos nor CRSP distribution codes are on disk.

**Mechanism.** The effect is concentrated, not diffuse. On PGR 2014 the put finished in the money
and the unadjusted strike charges the writer the full dividend through the put's intrinsic. If
OCC adjusted only the USD 1.00 special, that event's H rises by about 16% of m0. If the FANG
variable dividends were not adjusted, they belong in the early-exercise correction instead, at
a similar cost to the writer. Either way the block-level effect is below 0.01% of m0 per trade.
The live rule (`exdiv_decision`) skips these events anyway.

## A7. One tracked trial count

`a7_trial_count.py` writes `trial_count.csv` from the hash records' `dsr_trial_count`,
`research/ledger/trials.csv` and `docs/RESEARCH_STATE.md` section 1.

**Components.**

| Component | Trials |
|---|---|
| Hedged-hold additions, 1,533 to 1,544 | 12 |
| Numbered trials 1,545 to 1,628 | 84 |
| Alpha hunt 1 | 117 |
| 1,779 and 1,780 | 2 |
| Alpha hunt 2 | 228 |
| Niche hunt | 158 |
| Earnings-adjacent hunt | 43 |
| This lane, 2,832 to 2,840 | 9 |

**Totals, which depend on the pre-ledger base.**

| Base | Total |
|---|---|
| 1,506, the low working note | 2,159 |
| 1,532, the declared conservative input | 2,185 |
| 1,885, counting the 375-strategy model zoo as 375 trials | 2,538 |

Lanes L2 to L4 are not yet counted.

**Defects in the sources.**

- *The largest `dsr_trial_count`* in any hash record is 1,615. The 2026-11-12 records declare
  1,616 to 1,628 without that key, so `orient` under-reports by 13.
- *`research/ledger/trials.csv` cannot be parsed by pandas.* Line 69 has an unquoted comma in the
  1,780 verdict.
- *Its `n_trials_declared` column mixes meanings.* It holds per-record counts in some rows and
  cumulative counts in others, so its sum (27,325) means nothing.
- *It lists 1,779 and 1,780 in six rows.* These are two trials.

None of these files was edited.

**Recommendation.** Use 2,185 plus the L2 to L4 counts as the deflation input. The zoo-counted
2,538 is the conservative alternative.

**Mechanism.** A quarter of the 2,185 is exploratory hunting since 2026-11-13: 546 trials across
the four hunts. The expected best Sharpe under no edge rises with the count. Any future pass needs
a correspondingly higher bar.
