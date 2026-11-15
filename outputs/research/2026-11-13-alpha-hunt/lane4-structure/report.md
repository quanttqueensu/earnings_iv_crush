# Lane 4: trade structure and execution

## Verdict

A paired execution gain survives the held-out read, but no modified book is net positive on it.
This is cost recovery, not alpha. Every result is exploratory, because the block ledger records
all of broad 2025-26 as viewed. Trials 1,719 to 1,736 are in `trials.csv` (40 rows).

## Split and basis

Discovery: broad events entered in 2025, N=801. Held-out: broad events entered January to June
2026, N=419, read once after `freeze_2026-11-13.md`. Megacap 2023-24 (N=243) was scored with
discovery, so it is a cross-universe check, not a holdout. The hold and hedge arms reuse the
2026-11-02 tables, all blocks viewed, and are descriptive.

Every number is a paired difference against the base trade (15:59:00 bids at entry, 15:59:00
asks at the next-session exit) on the same events, in per cent of margin m0 = 0.20 x parity
forward + 15:59 bid premium, net of USD 0.65 per contract per leg per side, per trade.
Intervals are date-clustered bootstrap 95%, with a clustered t. Real data, zero spend.

For scale, the base book is -0.03 [-1.15, +1.03] on 2025 and -3.24 [-4.46, -1.85] on 2026 H1;
gross at the mid it is +4.38 and +1.69.

## Findings

**1. Sell at 15:45 instead of 15:59 on broad names, at the touch.** Held-out +0.50
[+0.32, +0.69], t 5.4, N=419; discovery +0.79 [+0.58, +1.02], N=801. The frozen touch-only clock
stack (15:45 bid, 15:30 ask) passes its paired rule held-out: +0.58 [+0.27, +0.87], t 3.8,
sign-flip null percentile 99.96, against +1.32 on discovery. The exit clock did not replicate
(+0.07 [-0.14, +0.29]); the entry clock carries the result. Driver check: the 15:45 mid equals
the 15:59 mid (-0.06 [-0.18, +0.06]), so the gain is spread, not drift. It sits entirely in
wide-spread names (held-out half-spread terciles -0.27, +0.17, +1.83) and is absent on
megacaps (-0.05 [-0.26, +0.16]). Typical size at the 15:45 bid is 14 contracts. The level of
this book held-out is still -2.66 [-3.79, -1.36].

**2. Package execution: large on paper, resting on two assumptions.** Full stack at fill
probability 1: +2.89 [+2.55, +3.25] discovery, +3.11 [+2.80, +3.42] held-out; the frozen 50%
fill arm gives +1.56 [+1.40, +1.71], t 19.6, N=419. The package cost is a share of each event's
own half-spread (0.391 at entry, 0.384 at exit), estimated on discovery events that had a late
package print: 187 of 801 at entry and 46 of 801 at exit. Those are a selected, tighter subset
(median half-spread 2.36% of mid against 6.88% without a print), and the share is extrapolated
to the remaining 77% and 94% of events. Fill probability has never been measured; the haircut
rows are arithmetic. The selection-robust lower bound (package only where a seller-side package
actually printed, at its own cost, touch elsewhere) is +0.15 [+0.10, +0.20] discovery and +0.31
[+0.25, +0.39] held-out. Median print size is 1 contract, with 8 contracts per event in the late
window. The entry levers overlap: clock +0.79 and package +1.36 combine to +1.62, not +2.15.
Even at fill probability 1 the held-out level is -0.13 [-1.24, +1.08].

**3. Not buying back is the largest lever, and still not enough.** Hedged hold to expiry minus
the buy-back: +1.91 [+1.67, +2.16] (2013-19, N=3,077), +1.74 [+1.43, +2.03] (2020-24, N=4,676),
+2.75 [+2.37, +3.11] (2025-26, N=1,597). Level of the hedged hold: -1.13, -1.23 and -0.10
[-0.89, +0.66]. The conditional rule on record (hold only below the causal 75th implied-move
percentile) is dominated by always holding: conditional minus unconditional -0.78, -0.52 and
-1.46, each interval below zero. The gain from holding is as large above the 75th percentile
(+2.88, +1.67, +3.50) as below it.

## Failed or null

- Buy back at 15:30: +0.52 on discovery, +0.07 [-0.14, +0.29] held-out; does not replicate.
- Buy back at 15:01: +0.14 [-0.49, +0.53].
- Causal tight-spread screen on the clock book: +0.77 [-1.01, +2.58] within tenor, N=734, null
  percentile 83.9; megacap -0.57, null 37.4.
- Any clock change on megacaps: zero.
- Strangle one implied move out against the straddle: -0.03 [-0.56, +0.49], N=560. It collects
  29% of the premium and halves the cost, netting the same. The sample is biased: 196 events lose
  a wing quote at exit (straddle +0.52 on the kept events, -1.29 on the dropped).
- Delta hedge from the reaction open: variance reduction 17 to 24%, carry cost -0.38, -0.44 and
  -1.35 [-1.89, -0.79]; the worst 1% of trades barely moves (-58.3 to -56.3).
- Index hedge of the overnight market move: correlation of base P&L with the SPY reaction-day
  return -0.03, so at most 0.1% of variance is removable.
- Unhedged hold: +1.75 to +3.17 against the buy-back, with standard deviation 16 to 18 against
  12; dominated by the hedged hold on risk.
- Post-event side (read only): the inversion test fails validation and confirmation, and new
  post-event option positions are negative at the touch.

## Not testable on disk

The intraday crush path (single-name ticks cover only 15:00 to 16:00 on the reaction day, and
`postea_quotes` is one snapshot a day); package fill probability and cost on names with no
package print; the impact of the book's own order at 15:45.

## The 15:45 entry on the hedged hold, scored (trials 1,737 to 1,740)

Added by the team lead from `r7_rerun_logged.log` and `r8_coverage_check.log`. Same basis as
above, as a level of the combined book, per trade, net.

The combination is not new. It was pre-registered on 2026-11-02 as trial 1,554 (resting entry
plus hedged hold, `research/execution/2026-11-02-maker-entry-hedged-hold/`), whose imputed book
was +0.64 to +0.79% of m0 with an interval reaching zero. The figures here agree.

| Block | 15:45 quote source | N | H + 15:45 entry, level | 95% CI | Coverage outcome-dependent? |
|---|---|---|---|---|---|
| broad 2013-19 | `entry_1545_chains` | 1,394 | -1.17 | [-1.84, -0.51] | No: H -1.32 covered, -0.98 not |
| broad 2020-24 | `entry_1545_chains` | 2,080 | -1.04 | [-1.67, -0.45] | No: H -1.20 covered, -1.25 not |
| broad 2025-26 | tick panel | 463 | +1.52 | [+0.22, +2.89] | Yes, see below |

The 15:45 lift on the hold is +0.15 [+0.09, +0.21] in 2013-19, +0.16 [+0.11, +0.22] in 2020-24
and +0.65 [+0.45, +0.86] in 2025-26, so the earlier entry clock does not carry back in time at
size. The package arm at an assumed 50% fill reaches -0.89 and -0.78 in the two clean blocks, and
only an assumed fill probability of 1 brings them to zero (-0.46 and -0.35, intervals spanning
zero). The naked hold has the same mean as the hedged hold with about 50% more dispersion (sd 16
to 19 against 12), so it is dominated in every block. Megacap shows no entry lift (+0.00
[-0.10, +0.11], N=48). The 2025-26 matched subset also contains the 2025 discovery events.
`r7_entry_on_hold.log` was left empty by the interrupted run; the figures are in
`r7_rerun_logged.log`.

**The 2025-26 level is not readable.** Of the 1,597 hold events in 2025-26, 463 have a
same-contract 15:45 tick quote; 672 have ticks on a different strike, and 462 have no tick row.
The tick files were pulled for the 2025-26 broad ledger (`outputs/research/oos_2026_ledger.csv`),
which drops events whose exit leg had no bid, and those follow large moves. Inside the tick
panel's own date range (January 2025 to June 2026), the 265 hold events without ticks average
H -4.98 [-7.31, -2.67] against +0.81 [-0.07, +1.64] for the 1,135 with them. Coverage therefore
selects on the outcome, the landmine named in the project rules. Reweighting the covered events
to the full block's tenor, implied-move and spread composition does not repair it (it raises the
level to +2.16, because the reweighting cannot see the dropped large moves). The honest full-block
estimate is H on all 1,597 events plus the cell-imputed 15:45 lift: +0.51 [-0.29, +1.26], with an
interval that is too narrow because it ignores imputation error.

## Next

Nothing more on stored data: in the two blocks where coverage is clean, the combined book loses
about 1% of m0 per trade, and the one positive reading is attrition-biased. The forward-test
addendum already drafted for trial 1,554
(`research/execution/2026-11-02-maker-entry-hedged-hold/forward_test_addendum.md`) is the clean
test, and it is the analyst's decision whether to adopt it.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt\lane4-structure\report.md
