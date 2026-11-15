# Lane J: is residual value a persistent property of a name?

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log` and logs `r1` to `r7`.
`diagnosis.log` holds the full round-by-round reasoning and every figure.

## Verdict

No. Thirty trials (2,051 to 2,080, all reserved numbers used); nothing survived the held-out read,
and no book is net positive at the touch. A name's total residual value is not a persistent
property a causal per-name estimate can find. The part that does persist moves value between the
next-day buy-back and the hedged hold without changing the total.

## Split and basis

Discovery 2013-18 (2,640 events, 233 names); held-out 2019-24 (5,113 events, 281 names), read
once after `freeze_J23_persistence.md` and `freeze_J28_short_eb_selector.md`. 2025-26 was not
used, because the block ledger marks it viewed for every family. The held-out block is clean by
the ledger but adjacent-viewed (round 1 lanes 2, 3 and 5 sorted on own-history moves, not
own-history residual value). Residual value is per unit of premium, per trade, net at the touch,
within implied-move tercile, tenor and year cells; multiply by about 0.211 to express it in m0.
Persistence statistics are name-mean correlations against a name-shuffle null.

Nearest closed study: `research/selection/research_name_persistence_exec.py` (megacap, ranked on
the move ratio, buy-back only). This lane ranks on the name's own residual P&L, covers the hold
and the buy-back, uses empirical-Bayes shrinkage, and measures persistence before selecting.

## Results

| Trial | Result | Block | Effect | 95% CI | Null pct | Label |
|---|---|---|---|---|---|---|
| 2,051 | Hold residual, year-to-year | discovery | r -0.004 | [-0.087, +0.075] | 46.6 | Fail |
| 2,059 | Extrinsic left at exit, split-half | 2013-15 vs 2016-18 | r +0.449 | [+0.297, +0.585] | 100 | Descriptive |
| 2,068 | Same, after spread, implied-move, tenor and jump-share controls | 2013-15 vs 2016-18 | r +0.347 | [+0.177, +0.491] | 100 | Descriptive |
| 2,064 | EB selector on low extrinsic at exit, scored on the buy-back | discovery | +0.079 premium | [+0.002, +0.153] | 98.7 | Exploratory; mostly spread |
| 2,073 | Frozen primary: 0-1 day hold persistence | held-out | r +0.011 | [-0.234, +0.271] | 55.0 | Fail |
| 2,078 | Frozen EB selector, 0-1 day events | held-out | +0.002 premium | [-0.122, +0.126] | 51.1 | Fail |
| 2,080 | All-tenor hold persistence after controls | held-out | r +0.115 | [-0.017, +0.244] | 96.7 | Exploratory; carried by a handful of names |

The extrinsic persistence is real but does not lift the total. Names whose straddles keep value
after the print pay it at the buy-back and earn it back on the hold: selecting them on the hold
(trial 2,069) gives +0.077 on the post-reaction leg and -0.124 on the buy-back leg, a total of
-0.048. Trial 2,064's +0.079 decomposes into extrinsic +0.074, gap cost -0.040 and lower costs
+0.045. It is +0.024 at the mid and +0.027 without five names, and its buy-back book is still
-2.43% of m0 [-3.77, -1.11]. Trial 2,080 falls to r +0.049 without five names (GS, UPS, STZ, GIS,
MAR) and to -0.009 without ten. The buy-back's held-out persistence (+0.184) falls to +0.062
after controls (trial 2,079), because the entry spread itself persists at r +0.67: the closed
spread gate.

## Iteration story

Round 1 found no persistence at all and diagnosed low power (per-event residual sd about 0.54
premiums). Round 2 lengthened windows and split the residual into components: the noisy gap cost
does not persist, while extrinsic at exit and the post-reaction hedged leg do, and they offset.
Round 3 showed the one discovery pass was mostly the spread gate. Round 4 tried using the
persistent split for the exit decision (it costs -0.21% of m0 per event, because holding beats
buying back for every name) and restricted to 0-1 day tenors, where the two exits coincide; that
discovery reading (r +0.43 on 25 names) was noise on held-out.

## Process note

In rounds 1 to 4 the 1st/99th winsorisation cut-offs and three pooled control betas were fitted
on the full panel, including 2019-26 outcomes. They carry no information about which names
persist; the held-out script restricts every fit to 2019-24.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneJ-name-persistence\report.md
