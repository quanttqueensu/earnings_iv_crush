# Lane D: a structural model of each name's earnings jump

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, `heldout.log` and
freeze note. The freeze's code and data fingerprints were re-hashed and all seven match; the
held-out run (`heldout.log`, 17:42:31 local) followed the freeze note (17:41:10).

## Verdict

The strongest result of either hunt, and still exploratory. A selector built from a calibrated
jump model passed its frozen rule on held-out 2013-18 on both outcomes, failed its second held-out
read on 2025-26 (same sign, not significant), and falls short of the project's t >= 3 bar on its
primary outcome. No block was clean for this feature family, and the signal's final form was
chosen from discovery bins. On 2013-18 the selected events' hedged hold is about break-even
(-0.08% of m0) against -1.03% for all scored events: the selector removes the hold's loss there
but does not make it pay. Trials 1,871 to 1,900, all reserved numbers used, and 2,081 (megacap
replication, frozen but not read because the sample cannot detect the effect).

## Split and basis

Discovery 2019-24 (N=4,633). Held-out 2013-18 (N=2,155 scored), read once after
`freeze_2026-11-13_m4_demeaned_richness.md`; second held-out read 2025-26 (N=1,463), a block
viewed many times before. The model's settings were tuned on 1997-2012 announcements, where no
option outcome exists. Effect: selected events' residual value minus the other events' in the same
implied-move tercile and tenor cell, per unit of premium, per trade, net at the touch, with
date-clustered 95% intervals and a cell-matched random null. Levels are in % of m0.

## The model

Each name's reaction-move scale is forecast in logs from its own decayed announcement history
(half-life 16 announcements), shrunk towards its two-digit SIC industry and the cross-section, with
an elasticity of 0.5 to the 250-session daily vol before entry, then causally recalibrated
(Mincer-Zarnowitz regression, five-year half-life). The model-fair straddle combines the pooled
empirical shape of standardised moves from earlier years, scaled by that forecast, with Black
diffusion at the market's own two-expiry diffusive variance. Richness R is the 15:59 mid over the
model-fair value, minus 1, less the median R of events in the prior 91 days. Treated: top tercile
of R, with breakpoints from strictly earlier dates.

Calibration (realised over predicted move variance, pooled): 0.984 on discovery, 1.062
[0.977, 1.154] on 2013-18 and 1.062 [0.956, 1.174] on 2025-26. Only the pooled ratio was checked
out of sample. On discovery the model failed the lane's own decile check (bottom decile 1.21
[1.006, 1.435], trial 1,890), and that check was not run on either held-out block. The market
over-prices the move: realised over market variance is 0.835 on 2013-18 and 0.705 on 2025-26.
On discovery, the model's gap to the market predicts the market's error with slope 0.41
[0.24, 0.54], t 5.2 (trial 1,891); that is in-sample, on the block that chose the normaliser and
the recalibration. Rank correlation with round 1's own-history ratio is 0.11, so this is a different signal.

How it differs from earlier work: the jump-richness study divided the implied jump by the name's own
past moves only; trial 1,623 forecast move size, not mispricing; the model zoo is reduced-form
machine learning.

## Held-out results

| Trial | Read | Block | N (treated) | Effect | 95% CI | t | Null pct | Label |
|---|---|---|---|---|---|---|---|---|
| 1,897 | Frozen primary, buy-back | 2013-18 | 2,155 (742) | +0.101 | [+0.037, +0.173] | 2.91 | 99.9 | Exploratory; passes its frozen rule |
| 1,899 | Same events, hedged hold | 2013-18 | 2,155 (742) | +0.108 | [+0.044, +0.182] | 3.17 | 99.9 | Exploratory; secondary |
| 1,900 | Primary inside jump-share and half-spread cells too | 2013-18 | 1,992 (671) | +0.090 | [+0.012, +0.170] | 2.20 | 98.9 | Right-driver check |
| 1,898 | Frozen primary, buy-back | 2025-26 | 1,463 (462) | +0.050 | [-0.021, +0.119] | 1.39 | 90.8 | Fail |

Hedged-hold level by richness tercile (% of m0, net at the touch):

| Tercile | 2013-18 | 2025-26 |
|---|---|---|
| Cheapest | -1.83 | -1.17 |
| Middle | -1.16 | -0.67 |
| Richest (selected) | -0.08 [-1.04, +0.88] | +2.40 [+0.92, +3.82] |

The ordering is monotone in both blocks. The selected 2025-26 hold is net positive with an interval
above zero, but that block is not clean, and its hold table already excludes events with a missing
exit leg. The 2,640 events of 2013-18 lose 275 with too little announcement history to score; those
have H -2.47% against -1.03% for the scored events. Excluding them is a pre-entry rule, so it is not
attrition on the outcome.

2013-18 was not clean for this question: round 1's trials 1,689 to 1,691 sorted on
implied-minus-forecast move richness over 2016-19, which the freeze's provenance section omits,
and the buy-back outcome was promoted to primary after discovery showed it above the hold. The
industry and global posteriors include other names' reactions dated on the entry day, which close
after the 15:59 decision; their weight is about one over the number of names, so the leak is
negligible. The conservative reading is one exploratory held-out pass below t 3 whose replication
failed.

Mechanism: on 2013-18 the selected events moved 0.076 less than implied, within cell, which is the
jump over-pricing the model claims. On discovery that gap was +0.004 and the gain came through the
exit mid instead, so the channel is not the same in both blocks. By year on 2013-18, 2014, 2017 and
2018 are positive and 2015 and 2016 negative.

## Iteration story

The first model was badly miscalibrated: its top predicted-variance decile realised 0.21 of the
prediction, because scaling by 60-day vol imported the spring 2020 spike and a few huge past moves
dominated. Estimation moved to logs, and the jump scale was made to follow vol only partly. The
second model calibrated in the middle deciles but over-predicted 2020-21; its selection failed (null
percentiles 62 and 93), and in m0 units the signal partly measured move size. The third used a
250-session vol, a decaying level correction and a scale-free ratio. It reached level calibration
(0.97) and passed the buy-back on discovery at t 2.2, about a quarter of which was the
term-structure jump share. In 2024 most events landed in the top third because the model's level
lagged, so the trailing 91-day median was subtracted (t 2.47). The fourth added the causal
recalibration and was frozen.

## Megacap replication (trial 2,081): not read, underpowered

The rule of 1,897 was frozen unchanged for the megacap events of the hedged-hold study
(`freeze_2026-11-13_megacap_replication.md`; code fingerprints re-hashed and matching). Only the
data source changed: quotes and the two-expiry split from the megacap 15:59 strips, which match
the hold table's strike and mid on all 1,183 usable events, and the model history and reference
population taken over broad and megacap events together, strictly earlier dates only. The signal
script loads entry-time columns only.

The universe is not unread: the hedged-hold megacap amendment read its unconditional book, and the
reverse-alpha panel on the same 1,794 events carried the term gate and `jump_richness`. It has no
row in `blocks.csv`, so any read would have been exploratory.

Of 1,794 events, 1,183 have a usable hold outcome (398 have no exit leg, 162 no hedge vol, 51 no
permno) and 1,104 reach a tercile, 324 treated and 780 control. The top-tercile share is 0.293
among usable events and 0.282 among the 524 dropped events with a signal, so attrition barely
changes who is selected, though the dropped events' outcomes are unknown and no-exit-leg events
lose.

Before any outcome was read, the minimum detectable effect (80% power, 5% two-sided, per unit
premium) came out at 0.135 to 0.141 from the broad blocks' clustered errors scaled to 324/780, and
0.108 from the protocol's analytic formula. Power is about 0.51 at the held-out +0.101 and 0.20 at
the discovery +0.056. A fail would say nothing, so the outcome was not read and trial 2,081 is
logged as not scored.

## What would confirm or refute it

Roughly twice the megacap sample, or the forward paper book, which is the only clean block left.
The selected tercile's hold level, not only the paired effect, is the number that matters: it must
be positive at the touch outside 2025-26.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneD-jump-model\report.md
