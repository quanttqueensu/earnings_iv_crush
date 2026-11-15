# Lane 3: option surface and flow state as a predictor of short earnings straddles

## Verdict

Nothing survived the held-out read. Twenty variants were scored (trials 1,689 to 1,708). None
reached t >= 3 on discovery, and the one frozen candidate (R5) reversed sign on held-out. Every
result is exploratory: the block ledger already records 2016-24 and 2025-26 as viewed for this
outcome with own-history and term-structure features. No reviewer gate was run, and the trials
are not yet in the project ledger or `docs/RESEARCH_STATE.md`.

## Split, data and basis

Discovery 2016-19 for the richness family and 2014-19 for quote-surface features. Held-out
2020-24, read once after `freeze_2026-11-13_R5.md`; 2025-26 read once as a secondary block.
Real data, 15:59 ET quote marks only, every cut causal.

Effect is treated minus untreated net buy-back P&L per unit of premium, per trade, round trip,
at the measured cost (1.2714% in, 3.0182% out, exit at the ask when there is no two-sided mid),
compared within cells of causal implied-move tercile by tenor bucket. Intervals are
date-clustered bootstrap, 5,000 draws. The null is the treated per-trade Sharpe on margin
against count-matched draws within cell.

## Findings

**1. Richness against the jump_share move forecast is not a selector** (exploratory, fails).
It is jump_share with the sign flipped (rank correlation -1.00), and so it is tenor (+0.83
with days to expiry). Top tercile, 2016-19: -0.076 [-0.128, -0.021], t -2.77, null percentile
0.0, N=1,601, 422 treated. The rich events do realise less (median move over implied 0.50
against 0.73), but what remains is diffusive time value still in the contract the next day.
Nothing monotone remains inside tenor buckets or implied-move terciles.

**2. Event richness against own history, R5** (exploratory, failed held-out). Implied event
move from the two-expiry jump split, minus the name's mean log move over its last eight events.
Discovery 2016-19: +0.071 [+0.010, +0.131], t +2.29, null 99.3, N=1,615, 494 treated, carried
by gap cost (-0.071 [-0.137, -0.005]) as the mechanism named. Held-out 2020-24: -0.013
[-0.045, +0.018], t -0.81, null 11.3, N=4,377, 1,488 treated; the gap-cost difference is gone
(-0.003 [-0.040, +0.034]). 2025-26: -0.018 [-0.078, +0.035], t -0.63, null 20.0, N=1,328, 492
treated. With the closed jump-richness study, this family is now negative on three periods.

**3. Stored lead: top-tercile iv_term_spread with bottom-tercile entry spread** (exploratory,
not confirmed). 2014-19: +0.087 [-0.006, +0.180], t +1.84, null 96.0, N=2,409, 398 treated.
Tight spread alone gives +0.055 [-0.006, +0.116], t +1.79, null 96.2, 741 treated, so most of
the lift is the spread, not the term spread. Not taken to held-out: it is below the bar, and it
needs re-scoring at each event's own quoted half-spread first, or it is the closed spread gate.

## Failed variants (discovery, effect in fractions of premium)

R1b richness top quintile -0.064 (wrong sign); R2 forecast with name history -0.068 (wrong
sign); R3 log implied move minus own mean log move +0.025, t 0.91; R4 bottom tercile of
jump_share -0.034; H6 concave smile on quotes +0.049, t 1.37, sign flips by tenor (favourable
at 0-1 days, reversed at 10 days and over); H7 bid-heavy displayed depth on the held legs
+0.004; H8 last-hour prints above the 15:59 mid -0.017; H10 large absolute wing skew -0.015;
H11 large absolute implied carry between expiries (borrow magnitude) -0.035; H12 displayed
depth thin against own history +0.029, t 1.10; R5 inside the 0-1 day tenor +0.149
[-0.010, +0.303], 134 treated, thin; H6 inside the 0-1 day tenor +0.110 [-0.037, +0.264], 201
treated, thin; R5 top quintile +0.062, t 1.74; R5 and concave together +0.084, 170 treated,
thin.

## Pivot evidence

Round 1 bins put the richest tercile at a median 21 days to expiry against 1 day, which drove
the move to the event component alone (R5). Round 2 bins showed concavity and own-history
richness monotone only in the 0-1 day tenor, which drove round 3 inside that tenor; those cells
are too thin to conclude.

## Not tested (usage window, not data)

Signed flow and closing imbalance (`data/cache/flow`, `fills`, `fills_et`; ticks cover only the
two traded contracts on broad 2025-26 and megacap 2023-24, and no flow was signed); the 5 to 10
session event-IV run-up (`dolthub_runup`, 2019-24); open interest and volume against own
history (the 15:59 chains hold the last print only); `entry_1545_chains`; `postea_chain`.

## What would confirm or refute

Stored lead and tight spread: a frozen 2020-24 test at each event's own touch. Concavity at
0-1 days: a frozen 2020-24 test in that tenor only, about 1,500 events, powered only for
effects near 0.10 of premium.

## Files

`trials.csv` (20 rows), `freeze_2026-11-13_R5.md`, `lib.py`, `s00_base.py` to
`s06_heldout_R5.py`, logs `s01`, `s02`, `s04`, `s05` discovery and `s06_heldout.log` (every
number above), and reusable per-event quote-surface features in `chain_features.parquet` and
`all_features.parquet` (9,350 events).

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt\lane3-surface-flow\report.md
