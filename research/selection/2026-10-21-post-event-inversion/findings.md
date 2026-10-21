# Inverted post-event term structure: the reversed-sign test and its confirmation

Draft for the analyst's signature. The numbers and the verdicts apply the frozen criteria
mechanically.

## Hypothesis, scope and success criteria

Formed after viewing E2's discovery result (stated in the pre-registration): names whose implied
term structure is still inverted at the reaction-session close outperform. Two trials.

1. Long the lowest post-event slope decile, short the highest, on 2019-2024, never viewed for
   this signal (`prereg.md`, ed6a87fe...). Pass: lower bound above zero; "promising" also required
   the effect to survive within reaction-return terciles and a clustered slope-rank t below -2.
2. After an exploratory beta check on the two viewed blocks, a beta-hedged long of the lowest
   decile on 2025-2026, the only untouched data
   (`research/selection/2026-10-21-inversion-confirm/prereg.md`, 5fad20ec...). Pass: lower bound
   above zero.

## Results

| Test | N | Mean net per 20-day position | 95% CI | Note |
|---|---|---|---|---|
| Long-short, 2019-2024 | 1,137 | +0.37% | [-0.29%, +1.02%] | slope-rank t -1.96; within-reaction-tercile average +0.34% |
| Exploratory, CAPM-adjusted gross, lowest decile, 2013-18 / 2019-24 | 318 / 690 | +1.27% / +0.98% | not computed | viewed blocks; beta 1.07 / 1.03 |
| Beta-hedged long of the lowest decile, 2025-2026 | 210 | +0.18% | [-1.08%, +1.37%] | minimum detectable effect 1.82% |
| Highest decile, 2025-2026 (secondary) | 89 | +1.29% | [-0.77%, +3.50%] | |

Confirmation data: yfinance adjusted closes, SPY hedge, 13-week bill; signal from the OPRA 15:59
chains; 2024 CRSP half-spreads (the permno taken from the ticker's last linked event, because CRSP
name records end in 2024); 1,630 of 1,684 events scored.

## Verdict

Both fail. The lowest-decile outperformance seen in the two blocks it was found in (about +1% over
20 sessions after beta) did not appear in 2025-2026 (+0.18%). That test was underpowered for an
effect of this size, so the honest reading is no evidence for the effect out of sample, not
evidence against it. Closed under the kill criterion.
