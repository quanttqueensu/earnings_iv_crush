# Second confirmation of the frozen ML ratio model: July-August 2026

## Hypothesis, scope and success criteria

The frozen ridge model of `outputs/research/ml_ratio/` failed its pre-registered rule (megacap
2022-2024 test failed) but passed the 2025-2026 broad confirmation strongly. This separately declared
test (`research/selection/preregs/ml_ratio_confirm2_prereg.md`, SHA-256 2fc1496c..., hashed before any feature or
outcome was built) applies the unchanged model and threshold to the 199 events of
`backfill_ledger.csv` (entries 2026-07-13 to 2026-08-06), data no test in the programme had touched.
Features: the same Alpaca code path as the 2025-2026 features. Outcomes: cached 15:59 chains, zero-bid
exit legs at ask / 2, 11.6%-of-premium cost, Reg-T margin. Pass required selected-minus-unselected
net RoM above zero with a date-clustered 95% interval above zero, and selected mean above zero.

## Results

| Measure | Value |
|---|---|
| Events with features and outcomes | 199 of 199 |
| Selected by the frozen threshold | 130 (65%) |
| Selected mean net RoM per trade | +0.42% |
| Unselected mean net RoM per trade | -0.88% |
| **Difference** | **+1.31% [-0.93%, +3.80%]** |
| Spearman(prediction, realised/implied), N=194 | +0.057 (bootstrap interval [-0.02, +0.22]) |

## Verdict

**FAIL.** The direction matches the 2025-2026 broad block (selected events do better, and the
prediction ranks realised/implied the right way), but the difference is about 1.3 points of margin
against about 8 in 2025-2026, and its interval includes zero. With 199 events the interval half-width
was about 2.4 points, as the power statement anticipated, so an effect of the 2025-2026 size would
have been detected; one of the size seen here is not distinguishable from zero.

## Where the ML line stands

Across three evaluation sets the frozen model's selected events beat its unselected events every
time on the broad universe (2025-26: +8 points; July-August 2026: +1.3 points) and not on megacaps
(2022-24: no ranking skill). Two pre-registered tests have failed. The consistent sign on broad names
is worth a forward paper test with the model frozen, scored on a pre-declared count (about 400
events, which gives an interval half-width near 1.7 points), but nothing here is evidence of a
tradable edge.

## Reproduction

```
python scripts/research_ml_ratio_confirm2.py --features
python scripts/research_ml_ratio_confirm2.py --score
```
