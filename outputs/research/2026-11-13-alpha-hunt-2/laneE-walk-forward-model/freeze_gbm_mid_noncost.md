# Freeze: gbm_mid_noncost (trial 1908 configuration), written 2026-11-13T17:36Z before any held-out read

Configuration. HistGradientBoostingRegressor (max depth 2, 150 iterations, learning rate 0.03,
at least 300 events per leaf, L2 1.0, half the features per split, seed 0) on the 167 non-cost
features of `feature_map.csv`, each ranked against its training values (ECDF), with missingness
indicators where training missingness exceeds 5%. Target: the hedged hold to expiry at the mid
(H_mid x m0 / mid0), demeaned within announcement quarter x implied-move tercile x tenor cell,
winsorised at the training 1st and 99th percentiles. Refit every calendar quarter on events
whose expiry fell before the quarter began; select events whose prediction exceeds the 80th
percentile of the model's predictions on the last four training quarters. Scorer `wf.py` (sha256
prefix 9656e806008a1a25, slate r5, trial 1921), inputs `panel.parquet` (12895e22e257f6d3) and
`feature_map.csv` (6f50d532546bf6b5).

Why this one. It is the strongest configuration whose form was stated before scoring (round 2)
rather than read off the decomposition, and it carries the least spread loading (prediction rank
correlation with the entry half-spread -0.075). The ensemble 1920 scored about the same but is
discovery-derived. Provenance: 1908 itself was motivated by the round 1 diagnosis (the touch
target rediscovers the spread gate), so it is a fix of a failed form, not a pre-stated idea.

Held-out block: test quarters 2022Q1 to 2024Q4, read once. Primary statistic: mean excess y of
the top-quintile picks over their same-quarter cell, hedged hold to expiry, net at the touch, per
unit entry mid premium, per trade, date-clustered 95% interval. Pass: interval above zero, null
percentile at least 95 against same-count random picks within quarter x cell, pooled rank IC
interval above zero, t at least 3. For the result to count as something beyond the spread gate,
the excess at the mid must also have an interval above zero. Level: mean H of the picks on m0,
net at the touch, reported beside it.

Power, stated before the read. Discovery gave +0.043 with an interval half-width of about
0.038 on 719 picks. With about 560 picks expected in 2022-24, the standard error is about 0.022,
so t >= 3 needs an excess near +0.066, above the discovery point estimate. A confirmatory pass is
improbable even if the discovery effect is real; the realistic informative outcome is the sign
and the interval.

Label. Exploratory at best: round 1 scored component features of these panels on residual value
with 2019-24 as its held-out block, so 2022-24 is partly viewed through the components.
After the read, the same frozen model is run once on 2025-26 (slate r5v, trial 1922) as a
descriptive figure; that block has no forensics rows and has been read by many earlier trials.
