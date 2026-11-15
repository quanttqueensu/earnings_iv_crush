# Freeze note: name persistence of residual value on the held-out block

Written 2026-11-13T17:24Z, before any 2019-24 outcome was read by this lane. The only 2019-24
quantities looked at are event and name counts per tenor (no outcome): 1,743 events with 0-1 day
tenor and causal cell; 94 names with at least three such events in each half; 258 names with at
least three events of any tenor in each half.

## Provenance

The all-tenor questions (J24, J25) were stated in round 1 before any outcome was read. The
restriction to 0-1 day tenors (J23, J26, J27) is discovery-derived: it was chosen after rounds 2
and 3 showed that the persistent components (extrinsic at exit, the post-reaction hedged leg)
offset each other in the total, and round 4 found the 0-1 day hold residual persistent on
discovery (trial 2,071: r +0.43 [+0.10, +0.69], null pct 98.0, only 25 names).

## Hypothesis and mechanism

A name's event straddle is chronically over- or under-priced relative to its tenor and
implied-move peers, through its option-market structure, its investor base or its dealers. The
effect is visible where the straddle is the event alone: with 0-1 day left after the reaction
session, the hold and the buy-back are nearly the same trade, so post-event decay cannot move
value between exits and the residual measures the event pricing. Prediction: positive
correlation of a name's mean residual value across 2019-21 and 2022-24.

## Statistic (identical code path to trials 2,057 to 2,061 and 2,071)

Residual = outcome winsorised at its 1st and 99th percentiles within the sample scored, less its
mean within causal implied-move tercile x tenor cell x announcement year. Name mean in each half
(2019-21, 2022-24), names with at least three events in each half. Pearson r across names.
Null: 5,000 permutations of the second-half means across names (seed 0). Interval: 5,000 name
bootstrap draws, percentile 95%. t = r / sd of the null.

| Trial | Role | Events | Outcome |
|---|---|---|---|
| 2,073 J23 | primary | 0-1 day tenor | y = H per unit mid premium, net at touch |
| 2,074 J24 | secondary | all tenors | y, net at touch |
| 2,075 J25 | secondary | all tenors | yb = B per unit mid premium, net at touch |
| 2,076 J26 | decomposition | 0-1 day tenor | y_mid = H_mid per unit mid premium, at the mid |
| 2,077 J27 | decomposition | 0-1 day tenor | y less OLS on entry half-spread, log implied move, days to expiry |

## Decision rule

J23 passes if the CI lower bound is above zero and the null percentile is at least 95. It is
confirmatory only if t is also at least 3; it cannot be, under the brief's labels, because the
tenor restriction is discovery-derived, so a pass is labelled exploratory (held-out
replication). Secondaries cannot rescue a failed primary. If J23 passes, J26 and J27 say
whether the persistence is the spread (gone at the mid or after controls) or something left
over; only a remainder that survives J27 is new.

Expectations stated now: J24 near zero (discovery all-tenor hold -0.029); J25 small positive
and carried by spread persistence (discovery +0.116, pct 92.9; after controls year-pair -0.010).

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneJ-name-persistence\freeze_J23_persistence.md
