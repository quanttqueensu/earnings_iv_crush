# Alpha hunt, five lanes: consolidated result

Artefacts (lane folders, scripts, logs and per-event files) are in `outputs/research/2026-11-13-alpha-hunt/`, which is shared through the R2 bucket, not git: `python -m earnings_iv_crush.data.sync pull --only outputs/research`. Paths below are relative to that folder unless they start at the repository root.

## Verdict

No selector survived a held-out read. Across 117 scored variants in five lanes (116 distinct
ids within 1,629 to 1,771, plus 1,644b; each lane's `trials.csv` is the count of record), the
only effects that hold out of sample are execution and holding levers, and they recover cost
rather than create an edge. Every gross-at-mid book is positive and every net-at-touch book is
negative or, at best, indistinguishable from zero. The edge in this trade is the spread the
seller pays, not which events are chosen.

Every figure below is copied from the lane logs; each lane's report gives its basis and file.

## Ranked results

| Rank | Result | Block | Effect | 95% CI | N | Label |
|---|---|---|---|---|---|---|
| 1 | Hedged hold to expiry minus next-session buy-back | 2013-19 / 2020-24 / 2025-26 | +1.91 / +1.74 / +2.75 % of margin | all above zero | 3,077 / 4,676 / 1,597 | Descriptive, viewed blocks |
| 2 | Sell at the 15:45 bid instead of 15:59, broad names | held-out 2026 H1 | +0.50 % of margin | [+0.32, +0.69] | 419 | Exploratory |
| 3 | Package execution, selection-robust lower bound | held-out 2026 H1 | +0.31 % of margin | [+0.25, +0.39] | 419 | Exploratory |
| 4 | Market within 2% of its 52-week high | held-out 2019-24 | +0.031 of premium | [-0.001, +0.064] | 5,713 | Exploratory, failed |
| 5 | Early reporter within its industry | held-out 2019-24 | +0.029 of premium | [-0.009, +0.066] | 4,550 | Exploratory, failed |

Levels, the number that matters: the hedged hold is -0.10% of margin [-0.89, +0.66] on 2025-26
and negative on both earlier blocks. The 15:45 clock book is -2.66% [-3.79, -1.36] on 2026 H1.
The full package stack at an assumed fill probability of 1 is -0.13% [-1.24, +1.08].

## The combined book: 15:45 entry plus hedged hold (trials 1,737 to 1,740)

Scored after the lanes finished (`lane4-structure/r7_rerun_logged.log`, `r8_coverage_check.log`).
In the two blocks where 15:45 quote coverage does not depend on the outcome, the combined book
loses: -1.17% of m0 [-1.84, -0.51], N=1,394 (2013-19) and -1.04% [-1.67, -0.45], N=2,080
(2020-24). The positive 2025-26 reading (+1.52% [+0.22, +2.89], N=463) is attrition-biased: the
tick pull follows a ledger that drops events with no exit bid, and the uncovered events in range
average H -4.98% against +0.81%. The full-block estimate is +0.51% [-0.29, +1.26], too narrow
because imputation error is ignored. This repeats trial 1,554 (2026-11-02), whose imputed book was
+0.64 to +0.79% with an interval reaching zero; its forward-test addendum is the clean test.

## Trial-id collision

The alpha hunt used ids from 1,629, the "next free" figure in `docs/RESEARCH_STATE.md`. The
resting-entry confirmation prereg written the same day
(`research/execution/2026-11-13-maker-entry-confirmation/prereg.md`) also claims 1,629 and 1,630,
and was frozen at 2026-11-13T17:02:06Z (prereg sha aeee3fcc) before the collision was raised. No
outcome has been computed for it, and that session will not score it until the numbering is
settled. Resolved the same day, before any outcome: amendment 01
(`research/execution/2026-11-13-maker-entry-confirmation/amendment_01_renumber.md`, sha
6f6277c9, record `outputs/research/prereg_2026-11-13-maker-entry-confirmation-amendment-01.json`)
renumbers that study's trials to 1,779 and 1,780. The span 1,629 to 1,778 belongs to this hunt,
so the next free number is 1,781.

## What each lane closed

- Macro (lane 1): 24 hypotheses, none in the pre-stated direction; the macro-release near miss
  sits only in the hedged hold and is a composition effect; an index hedge removes at most 0.1%
  of variance.
- Forensics (lane 2): every group earns about +9 to +14% of premium gross at the mid; liquidity
  and size rules reproduce the closed spread gate. No held-out read.
- Surface (lane 3): richness against the move forecast is tenor under another name; event
  richness against own history reversed sign on 2020-24 and 2025-26.
- Structure (lane 4): exit clocks, strangles, the reaction-open delta hedge and the conditional
  hold rule all fail or are dominated; always holding beats the conditional hold in every block.
- Niche (lane 5): 21 calendar and cross-section features fail; the one discovery-derived
  candidate shrank by three quarters out of sample.

## Process notes

Two discovery-derived candidates (avoid high VIX, early in industry) were formed by reversing a
failed pre-stated direction; both failed held-out, as expected. No `quant-reviewer` gate was run
on these slates, and none of these trials is yet in `docs/RESEARCH_STATE.md` or
`research/ledger/blocks.csv`.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt\SUMMARY.md
