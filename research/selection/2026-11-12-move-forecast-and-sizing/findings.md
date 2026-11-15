# Forecasting the size of the earnings move, and sizing the book on it: findings (draft, verdict unsigned)

Corrected after an independent post-run review. Figures trace to `results.json`,
`corrections.json` and the two logs in `outputs/research/2026-11-12-move-forecast-and-sizing/`.

## Hypothesis, scope and success criteria

Part A (trial 1,623): non-price information forecasts the log absolute earnings reaction better
than the implied move alone. Part B (trials 1,624 to 1,628): risk-equalised or budgeted sizing
raises the per-date Sharpe ratio of the unconditional next-day buy-back book against fixed
contracts. Frozen in `prereg.md`, SHA-256
`31fadef27c03c26c18b762de5d2eb0d67c6f4ff37cd6fc178757916fa43d39ac`, recorded
2026-11-12T15:46:45Z before any outcome. Part A passes if the out-of-sample squared-error gain of
M1 over M0 has a date-clustered 95% interval above zero on 2016-24 and a positive point on
2025-26. A Part B scheme passes if its per-date Sharpe minus fixed contracts has a pooled 2016-24
interval above zero and a positive point in each sub-block, on the measured basis.

## Funnel

9,350 events (2013-24 ok rows plus 2025-26 confirm). 1,597 confirm events lacked a permno; 1,546
were mapped from the ticker's earlier permno, 51 were not. Characteristics matched 7,527. Exit at
the ask because no two-sided exit mid: 2,192 events, kept. Out of sample from 2016: 8,107 events,
M1 defined on 6,427 (79.3%).

## Part A: option term-structure information forecasts the move; non-price information adds little

**Scorer deviation.** `study.py` fitted M0 on every training event; the prereg fits both models on
the same events. Refitted as frozen (`corrections.py`), the result still meets the frozen rule:

| Block | N | MSE gain, M1 over M0 (as frozen) | Verdict under the frozen rule |
|---|---|---|---|
| 2016-2024 | 5,242 | +0.0411 [+0.0275, +0.0555] | interval above zero |
| 2025-26 | 1,185 | +0.0209 [-0.0077, +0.0509] | positive point; interval spans zero |

The scorer's original figures (+0.0480 and +0.0146) are superseded. The 2025-26 rule needed only
a positive point estimate; that rule was lenient and the block is not significant on its own.

**What carries the gain** (descriptive attribution, same common-sample M0, same intervals):

| Inputs added to the implied move | 2016-2024 | 2025-26 |
|---|---|---|
| Term-structure event share only (`jump_share`) | +0.0463 [+0.0345, +0.0587] | +0.0177 [-0.0092, +0.0450] |
| All non-price inputs, without `jump_share` | +0.0135 [+0.0036, +0.0236] | +0.0109 [-0.0076, +0.0284] |
| Everything (M1 as frozen) | +0.0411 [+0.0275, +0.0555] | +0.0209 [-0.0077, +0.0509] |

The gain is carried by `jump_share`, the share of front variance the term structure assigns to
the event. That is option information, so the hypothesis as stated (information outside the
option price) is not supported: the non-price inputs add +0.0135 on 2016-24 and nothing
distinguishable from zero on 2025-26, and adding them to `jump_share` lowers the gain. Out-of-
sample R^2 is low throughout (0.055 to 0.095 on 2016-24) because one reaction is one draw from a
wide distribution. Term-structure gates are closed for money (`docs/RESEARCH_STATE.md`), so this
is a forecasting result with no monetisation shown.

## Part B: the primary statistic could not answer the question

The book's per-event mean is negative on both bases, 2016-24: -1.25% of margin [-1.57%, -0.94%]
measured and -3.03% [-3.36%, -2.70%] at the touch (N=6,510, 1,201 date clusters). This was knowable
before freezing. With a negative mean, per-date Sharpe rewards whichever weighting diversifies
least, so the pre-registered comparison measures concentration, not sizing quality, and drawdown
in sd units is dominated by drift. **No Part B verdict, pass or fail, is informative**, including
the touch-basis passes of S5 and S6. The scheme table is in `results.json` and is not reproduced
here to avoid it being read as evidence.

Descriptive only: equal-premium sizing (S3) cuts the share of total loss carried by the worst 1%
of events from 24% to 12% (pooled 2016-24, measured basis), which is close to mechanical once
weights are equalised, while its maximum drawdown in sd units roughly doubles (158 to 312). Neither
figure answers whether sizing improves the book; that needs a statistic valid for the sign of the
mean (for example a loss budget or expected shortfall per unit of premium) on a block where the
mean is not negative.

## Process failures in this study

- Part B's primary statistic was ill-posed for a negative-mean book, a fact visible before the
  freeze.
- Part A's prereg called `jump_share` part of a non-price model; the hypothesis and the model did
  not match.
- M0 fit sample deviated from the frozen text (corrected above).
- The first draft quoted figures with no logged source (now in `corrections.json`) and omitted the
  drawdown doubling.
- Study 2 was frozen after own-history numbers on 2020-26 had been viewed in the tail study, and
  then used own-history features on those blocks.

## Trial accounting

Trials 1,623 to 1,628 used. Next free: 1,629. `corrections.py` is not a trial. Row in
`docs/RESEARCH_STATE.md` drafted, unsigned.
