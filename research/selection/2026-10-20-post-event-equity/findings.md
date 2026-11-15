# Post-event option surface and the stock's next 20 sessions

Draft for the analyst's signature. The numbers and the verdicts apply the frozen criteria
mechanically.

## Hypothesis, scope and success criteria

E1: high post-event 25-delta put skew predicts underperformance (long the lowest decile, short the
highest). E2: an inverted post-event term structure predicts underperformance (long the highest
slope decile, short the lowest). Traded in the stock at measured CRSP closing half-spreads.
Pre-registration `prereg.md` (034203dc...). Pass: lower bound above zero in discovery (exit dates
2013-2018) and validation (2019-2024). Real data.

## Results (discovery, 2013-2018)

| Signal | Positions | Mean net per 20-day position | 95% CI | Sharpe per position | Median round-trip cost |
|---|---|---|---|---|---|
| E1 skew | 451 | -0.28% | [-0.96%, +0.36%] | -0.043 | 2.4 bp |
| E2 term slope | 486 | -0.91% | [-1.64%, -0.18%] | -0.115 | 2.5 bp |

Funnel: 9,567 events, 9,467 with a full 20-session window and quotes.

## Verdict

Both fail discovery and are closed as declared. E2 failed with its sign significantly reversed:
the lowest-slope decile earned +1.40% gross market-adjusted, the highest +0.13%. That reversal was
tested as a new hypothesis in `research/selection/2026-10-21-post-event-inversion/` and its
confirmation in `research/selection/2026-10-21-inversion-confirm/`.
