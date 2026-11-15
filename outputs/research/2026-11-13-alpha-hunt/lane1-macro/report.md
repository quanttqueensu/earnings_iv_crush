# Lane 1: macro and market-wide state as a predictor of short earnings straddles

## Verdict

Nothing survived the held-out read. Twenty-four hypotheses were scored on discovery (2013-18,
trials 1,629 to 1,654) and none passed in its pre-stated direction. Two candidates were frozen
(`freeze_2026-11-13.md`) and read once on 2019-24; both fail. 2025-26 was not read. Trial ids
1,655 and 1,658 are unused.

## Split, data and basis

Discovery 2013-18 by entry date; held-out 2019-24; 2025-26 reserved for a held-out pass only.
Panel `panel.parquet`: 10,533 scoreable events (broad 2013-26 and megacap 2013-24) on 1,981
entry dates, real data. Discovery N=3,022; held-out N=5,713 on 920 dates in 72 months.

Delta is treated minus untreated next-session buy-back P&L, net at the touch, per unit of entry
premium, per trade, compared within implied-move tercile by tenor cells. Intervals are 95%,
clustered by entry date, with a month-clustered check. Nulls are a cell-matched random
selection and a date-rotation placebo. The book mean is negative (-0.127 discovery, -0.129
held-out), so no Sharpe or sizing comparison was used.

## Held-out results (`r4.log`)

| Candidate | Treated | Delta | 95% CI (date) | t | Null pct (cell / shift) | Verdict |
|---|---|---|---|---|---|---|
| C2 SPY within 2% of 250-session high at prior close (direction pre-stated) | 2,531 on 440 dates | +0.031 | [-0.001, +0.064] | 1.84 | 97.8 / 93.3 | Fail |
| C1 prior-close VIX below expanding top tercile | 2,235 on 381 dates | +0.019 | [-0.015, +0.054] | 1.06 | 85.7 / 88.6 | Fail |

C2 matches its discovery sign and size (+0.037 [-0.010, +0.086]) but the treated mean is still
-0.119 of premium: it would trim losses, not create an edge. C1 came from reversing the
pre-stated direction after seeing discovery (-0.076 [-0.124, -0.029], t -3.15, 783 treated on
195 dates in 30 months), with mechanism checks already unsupportive; on held-out it has the
wrong sign in four of five usable years.

## The macro-release near miss, explained and closed (descriptive)

The earlier +0.08 exists only on the hedged-hold outcome. On the overnight buy-back it is +0.032
[-0.051, +0.113] at the touch and -0.015 at the mid. Realised over implied move (0.751 against
0.760) and the absolute SPY move are the same on release days, so the effect is neither index
move nor surprise size; it sits in the post-reaction hold, on 08:30 releases, with a different
session and tenor mix. A fresh 2013-15 replication gives +0.036 [-0.049, +0.109], 211 treated on
44 dates, null percentile 80.9; the 08:30-only variant gives +0.009. No sharper point-in-time
version is justified.

## Index hedge (descriptive)

Correlation of P&L with the beta-scaled absolute SPY move is -0.013 [-0.051, +0.026], N=3,019,
so long index gamma could remove at most 0.02% of variance before cost.

## Failed hypotheses

VIX level high (opposite sign, did not hold out); VIX five-day spike; VIX9D over VIX contango;
VIX minus realised; name IV over VIX; credit tightening; quiet 10-year yield; no release near
the trade; calm season over the last ten days; late season; VVIX; Friday reaction (-0.099 in
2013-15 only, gone 2016-18); low expected market share (beta times VIX over implied move);
08:30 release replication; busy reporting day; quiet prior tape; quiet dollar; pre-FOMC window;
SKEW; calm composite; high beta inside high VIX (mechanism check, not supported); VIX falling
over 20 sessions; implied-correlation proxy (duplicates VIX level). 2s10s was not testable
(a single regime).

## Why macro state fails here

The stock's own earnings jump dominates the outcome. The market component is roughly 7 to 20%
of the implied move and adds in quadrature, and touch costs do not vary with macro state.

## Not tested

Priced SPY overnight implied move from `data/cache/index_chains`, a true implied-correlation
index, and high-yield spreads.

## Housekeeping

`research/ledger/blocks.csv` was not edited (outside the lane folder). It needs rows for the
buy-back and hedged-hold outcomes on 2013-18 and 2019-24 against the macro-state family.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt\lane1-macro\report.md
