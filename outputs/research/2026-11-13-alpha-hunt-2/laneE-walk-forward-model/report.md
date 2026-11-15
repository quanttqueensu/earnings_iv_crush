# Lane E: a walk-forward combination of the round 1 features

Compiled by the team lead from this folder's `trials.csv`, `diagnosis.log`, round logs and freeze
note. Every figure is from those files.

## Verdict

No configuration survived the held-out read, and no selected book is net positive at the touch.
A combination of round 1's 184 point-in-time features ranks residual value slightly, but most of
what a model trained on the net outcome finds is the spread gate, which is closed. The part left
once the spread is taken out of the target is small, shrank by about a third out of sample, and
failed its frozen read. Trials 1,901 to 1,922; 1,923 to 1,930 unused.

## Split and basis

Walk-forward: refit each quarter on events announced before it, predict the next quarter.
Discovery 2016Q1 to 2021Q4; held-out 2022Q1 to 2024Q4, read once after
`freeze_gbm_mid_noncost.md`; 2025-26 viewed for everything and read only descriptively. All
results are exploratory, because round 1 scored these panels' single features on 2019-24.

"Excess" is the mean residual value of the top-quintile picks over their same-quarter cell
(implied-move tercile by tenor), on the hedged hold to expiry, per unit of entry mid premium, per
trade, net at the touch unless marked "at mid". Intervals are date-clustered 95%; the null is
same-count random picks within quarter and cell. H is the book level in m0, net at the touch.

## Results

| Trial | Configuration | Block | Excess | 95% CI | t | Null pct | Label |
|---|---|---|---|---|---|---|---|
| 1,903 | Depth-2 boosted trees, all features, net target | discovery | +0.076 | [+0.040, +0.113] | 4.10 | 100 | Mostly the spread gate |
| 1,909 | Boosted trees on the cost features alone | discovery | +0.067 | [+0.029, +0.105] | 3.44 | 100 | The spread-gate reference |
| 1,908 | Boosted trees, no cost features, trained at the mid | discovery | +0.043 | [+0.005, +0.081] | 2.22 | 99.1 | Frozen |
| 1,921 | Frozen 1,908 | held-out 2022-24 | +0.031 | [-0.016, +0.077] | 1.32 | 93.9 | Fail |

On held-out, 624 of 2,784 events were picked. The excess at the mid was +0.030
[-0.014, +0.073], the pooled rank correlation of prediction with outcome +0.032
[-0.009, +0.072], and the picks' book H was -0.52% of m0 [-1.49, +0.42]. The sign held in every
held-out year (rank correlation +0.020, +0.031 and +0.031). The freeze note stated before the
read that t >= 3 needed an excess near +0.066, above the discovery estimate, so a confirmatory
pass was improbable even if the effect is real. Read descriptively and selection-biased, the
out-of-sample rank correlation at the mid over 2016-24 is +0.045 [+0.020, +0.071] (N=6,510),
positive in 25 of 36 quarters.

## Iteration story

Round 1: four model families all passed discovery at the touch (+0.042 to +0.076), but their
predictions correlated -0.52 to -0.69 with the entry half-spread. Because the target is net of
the half-spread paid, the models were rebuilding the spread gate; at the mid the excess fell to
+0.016 to +0.044. Round 2 trained on the mid outcome and dropped the cost features, which kept
+0.043 to +0.050 at the mid with weak spread loading. Round 3 decomposed by feature group: the
option-surface group alone (+0.041 at the mid) and the price-path group alone (+0.039) each
matched the full model, while their picks barely agreed (rank correlation +0.07), so these are
two weak signals. Own history, fundamentals and filings, peers, macro and calendar each failed
alone. The excess is a broad shift, not a few winners, but dropping 2017 takes every candidate's
interval across zero. Round 4 restricted the model to the event-pricing groups and averaged
learners; the restriction made it worse even within discovery. Every working variant sits at
+0.03 to +0.05 at the mid: one diffuse signal that tuning does not sharpen.

On held-out, a few large losers sat among the picks (STZ 2022-04 -4.42, DFS 2023-07 -3.09 and
GILD 2022-10 -2.88 of premium), and the bottom-quintile avoidance seen on discovery vanished.
2025-26 cannot be read: the forensics panel has no rows there, and the missing features shift the
whole prediction distribution.

## Use for the project

A real but small and decaying ranking skill, far below what pays the spread. No clean block is
left to test a refinement, so a forward record is the only way to settle whether +0.03 of premium
is real.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-alpha-hunt-2\laneE-walk-forward-model\report.md
