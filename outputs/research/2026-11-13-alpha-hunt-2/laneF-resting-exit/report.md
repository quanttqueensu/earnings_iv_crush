# Lane F: resting orders on the buy-back exit

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log` and freeze note. Every
figure is from those files; `diagnosis.log` has the full reasoning.

## Verdict

One rule passed its frozen held-out read on broad names: bid at the mid on each leg and re-price
it every minute from 15:00, crossing whatever has not filled at 15:59:00. It fails on megacaps.
It is labelled exploratory, because the earlier F1 study had looked at a resting exit on both
blocks. No book is net positive at the touch. The resting buy-back recovers about a third of the
exit half-spread, which is about a third of what the hedged hold gains over the buy-back. It is
therefore not competitive with the hold, and a hybrid (rest, and hold hedged if nothing fills)
loses to always holding. Trials 1,931 to 1,958; 1,959 and 1,960 unused.

## Split and basis

Discovery: broad events entered in 2025 (N=802). Held-out, read once after
`freeze_2026-11-13_repeg-exit.md`: broad events entered January to June 2026 (N=419) and megacap
2023-24 (N=243). Every effect is per trade, in m0, paired against buying back both legs at the
15:59:00 asks on the same events, with date-clustered 95% intervals. Fill rule: a print at or
through the limit, or the ask reaching it; a stricter through-only rule is shown as a
sensitivity.

What F1 had measured: a static bid at the 15:00 mid against the 15:59:59 ask, +0.68% of margin
on broad names and +0.35% on megacaps, with entry and exit markouts pooled. It had not measured
the 15:59:00 basis, re-pegging, resting one leg, results in m0 or by gap, exit-only markouts,
coverage, or any link to the hold.

## Coverage

All 2026 broad ledger events have ticks, but the ledger depends on the outcome. Of 1,691 events
in the 2025-26 hold universe, 1,180 have ticks; the buy-back B averages -1.41% of m0 on covered
events against -6.32% uncovered, and covered events moved less (4.2% against 5.4%). Every broad
level is therefore flattered. Reweighting to the universe's move distribution leaves the gain at
+0.79% and lowers the 2026 level to -2.74%. All 243 megacap events are covered. The tick-based
taker book reconciles to the hold table's B on matched strikes (median gap 0.0002 of m0,
correlation 0.9994, N=531).

## Results

| Trial | Result | Block | N | Effect | 95% CI | t | Label |
|---|---|---|---|---|---|---|---|
| 1,951 | Re-pegged mid bid (frozen H1) | broad 2026 | 419 | +0.81% | [+0.63, +1.00] | 8.8 | Exploratory, held-out pass |
| 1,952 | Same, minus a taker at a random minute (frozen H2) | broad 2026 | 419 | +0.75% | [+0.58, +0.92] | 8.6 | Exploratory, held-out pass, null pct 100 |
| 1,957 | H1 with through-only fills (post-freeze) | broad 2026 | 419 | +0.71% | [+0.53, +0.89] | 7.8 | Sensitivity |
| 1,953 | Re-pegged mid bid (frozen H1) | megacap 2023-24 | 243 | +0.02% | [-0.19, +0.23] | 0.2 | Fail |
| 1,954 | Same, minus a random-minute taker (H2) | megacap 2023-24 | 243 | +0.09% | [-0.03, +0.22] | 1.5 | Fail, null pct 94 |
| 1,955 | Resting buy-back minus hedged hold, same contract | broad 2026 | 401 | -1.74% | [-2.43, -0.98] | -4.7 | Descriptive |

The random-minute null varies only the minute of a taker exit, not the events, so it isolates
liquidity provision from the time-of-day spread pattern. On broad 2026, 84% of events fill at
least one leg and 55% both; the five-minute markout is -0.57 half-spreads. The gain is flat
across reaction-gap sizes (+0.77, +0.96, +0.72 and +0.53% for moves under 0.5x, 0.5 to 1x, 1 to
2x and over 2x the implied move; N 197, 122, 90 and 9), because the in-the-money leg's dollar
spread grows with the gap. On megacaps fills are near certain (99%) but the five-minute markout
is -1.06 half-spreads: on tight quotes, a bid at the mid fills only when the mid is about to fall
through it.

Level: the broad 2026 resting book is -2.45% of m0 [-3.63, -1.11], against -3.26% for the taker
book, on a sample already flattered by attrition.

## Iteration story

Round 1: the static resting bid gained +0.47%, but simply lifting the asks at 15:00 gained
+0.41%; most of the gain was the clock, since the half-spread is 0.6% of m0 narrower at 15:00 to
15:45 than at 15:59. Round 2 paired the rules against takers at the same clock: +0.28% net of a
15:00 taker, and not significant net of a 15:30 taker. Adverse selection (-0.8 half-spreads at
five minutes) ate about half of what mid fills captured. Round 3: a ladder (patient first, mid
late) turned out to be pure clock. Comparing with the hedged hold mixed two contracts, since only
30% of 2025 events share a strike between the tick panel and the hold table. Round 4 compared on
one contract and replaced the fixed taker clocks with the random-minute null, then froze the
re-pegged mid bid. On held-out 2026 the random-minute taker earns about nothing, so the whole
gain is liquidity provision.

## Use for the project

A resting exit is a real execution improvement on broad names, but holding hedged beats it by
about 1.7% of m0, and by roughly 0.2% more under the expiry netting adopted on 2026-11-13, which
lifts the hold and not the buy-back (not recomputed on 2026). It matters only for events that are bought back rather than held, which under
the current evidence is none.

## Housekeeping

`ticks.parquet` (282 MB of raw vendor rows) was deleted after scoring; `extract.py` rebuilds it
from `data/cache/flow`. `events.parquet`, `path_panel.parquet` and `results/*.parquet` hold
per-event quote-derived prices and must not be committed.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneF-resting-exit\report.md
