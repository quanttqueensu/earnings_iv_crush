# W1: resting orders on the earnings straddle (F1) and customer demand pressure (F2)

## Hypothesis, scope and success criteria

Every liquidity-taking version of the earnings straddle failed net of the spread. F1 asks whether a
book that **provides** liquidity, resting a limit at the 15:00 mid on each leg and crossing at
15:59:59 only for legs still unfilled, recaptures enough of the spread to pay, without being picked
off by informed flow (spreads widen before earnings: Goyenko et al. 2015; Muravyev, Journal of
Finance 2016, on inventory and adverse selection). F2 asks whether net signed customer volume before
entry predicts the straddle's return (de Silva, So and Smith, Review of Finance 2026).

Pre-registration `research/execution/preregs/flow_liquidity_side_prereg.md` with addendum 01 (frozen before any
outcome: fills on a print through the limit or a quote at or through it; unfavourable tick rounding;
markouts; entry and exit arms; early-close exclusion; reconciliation gate) and addenda 02 and 03
(below). Data: Databento OPRA `cmbp-1` ticks for the two traded contracts of every event, from 09:30
two sessions before entry to the entry close, and the exit day's last hour. Blocks: the 2025-2026
broad ledger events and the 2023-2024 megacap events.

**Go criteria per block (all required, under both fill rules and both tick schedules):** paired
improvement (resting minus crossing, return on margin per trade) at least +0.65% with a
date-clustered 95% interval above zero; mean 5-minute markout no worse than -0.5 of the half-spread
captured; both-leg entry fill rate at least 30% under the strict rule.

## Process notes (amendments made before any paired outcome was viewed)

- **Addendum 02.** Exit-day tick files begin at 15:00:00, so the limit reference falls back to the
  first quote in the next minute when no quote precedes 15:00:00. The first scoring attempt had
  returned no measurable event for this reason.
- **Addendum 03.** The reconciliation gate stopped the second attempt (34.7% of events over the
  1%-of-margin tolerance). A diagnostic showed the tick data reproduce the cached chain exactly at the
  chain's own sampling instant (15:59:00: median gap 0.0, no event over tolerance, N=1,223) and that
  the gap came from comparing a 15:59:59 cross with the 15:59:00 chain. The gate now compares like
  instants; the paired F1 test is unchanged. Final reconciliation: 1,122 events matched, median gap
  0.0, none over tolerance.

## Funnel and spend

1,464 events planned; 1,357 measured; 107 unmeasurable (a leg unquoted at 15:00 or 15:59:59); no
early-close sessions. Databento spend USD 5.15 against a USD 10 cap; the USD 2.12 estimate priced
the broad block only, on a sample that excluded the heaviest names, and did not include the 2023-2024
megacap requests.

## F1 results

Primary arm: both legs resting, penny ticks. Returns on margin per trade; date-clustered 95%
intervals, 5,000 draws, seed 0.

| Block | N | Rule | Improvement [CI] | Resting Sharpe [CI] | Crossing Sharpe | Entry / exit both-leg fill | 5-min markout |
|---|---|---|---|---|---|---|---|
| Broad 2025-26 | 1,120 | strict | +2.06% [+1.82, +2.32] | +0.076 [+0.008, +0.151] | -0.101 | 61% / 50% | -0.68 |
| Broad 2025-26 | 1,120 | optimistic | +2.13% [+1.88, +2.39] | +0.081 [+0.013, +0.157] | -0.101 | 63% / 52% | -0.63 |
| Megacap 2023-24 | 237 | strict | +0.48% [+0.25, +0.72] | -0.103 [-0.212, +0.023] | -0.141 | 92% / 81% | -0.93 |
| Megacap 2023-24 | 237 | optimistic | +0.49% [+0.27, +0.73] | -0.102 [-0.211, +0.024] | -0.141 | 93% / 82% | -0.89 |

Split by arm (strict, penny): broad entry-only +1.38%, exit-only +0.68%; megacap entry-only +0.12%,
exit-only +0.35%. The non-penny schedule changes nothing material.

**Verdict: FAIL in both blocks.** The broad block clears the improvement, interval and fill-rate
gates and fails only the markout gate: five minutes after a fill the mid has moved against the
resting order by about two-thirds of the half-spread captured. The megacap block fails the
improvement gate and the markout gate.

## Robustness: the crossing baseline (descriptive)

The pre-registered crossing book trades at 15:59:59. In the final minute the touch moves sharply
against a taker: crossing at 15:59:59 costs 0.92% of margin per trade more than crossing at
15:59:00 on the broad block (median 0.20%) and 0.65% more on megacaps. Measured against a 15:59:00
cross, the programme's established taker basis, the improvement is **+1.14%** (broad) and **-0.17%**
(megacap). The resting book's own mean return is +0.87% of margin per trade on the broad block and
-1.22% on megacaps.

## Reading

1. Resting orders recapture a real part of the spread on the wider-spread broad names, and fills are
   frequent. But the fills are adversely selected (markout -0.68 to -0.93 of the half-spread in
   both blocks), which is the risk the hypothesis named, and a strict "touch equals fill" model
   ignores queue position, so live fills would be fewer and worse.
2. On liquid megacaps there is little spread left to capture; the maker book does not beat a
   15:59:00 cross.
3. The broad block is drawn from the 2025-26 ledger, whose attrition removes large moves
   (`oos_2026_attrition_audit`). The positive resting Sharpe there is measured on a sample that
   favours the short straddle and should be read as an upper bound; the megacap block, which does
   not have that tilt, shows no edge.
4. A practical result for any live execution: do not cross in the final seconds. The 15:59:59 touch
   is on average almost a full point of margin worse than the touch a minute earlier.

## F2 (discovery, broad block)

N=1,078 events with enough signed volume. Decile Spearman of net return on premium against
pre-entry imbalance +0.28; top-minus-bottom quintile +3.30 points of premium, CI [-3.55, +10.23];
imbalance against implied move Spearman +0.06. **Fails discovery**; not extended (P4 closes).

## Trials

F1 (two blocks) and F2 count as declared in the pre-registration. Programme ledger about 1,509.

## Reproduction

```
python scripts/research_flow_liquidity.py --score
```
Outputs: `events.csv`, `markouts.csv`, `f1.csv`, `f2.csv`, `verdict.json` in this directory.
