# Pre-registration: a machine-learned predictor of realised over implied move

## Hypothesis

Single at-entry variables (term slope, skew, kurtosis, curvature, richness, peers, date shift) have
each failed to select better earnings straddles. Many weak predictors combined non-linearly may
still rank events by how much of the implied move will be realised, which is the mispricing the
short straddle earns (design inputs 1 and 3). A model trained on early years, chosen on middle
years and frozen is tested once on later years and once more on a separate block. Closest prior
work: Gu, Kelly and Xiu (RFS 2020) for tree models on cross-sectional predictors; for options,
Bali, Beckmeyer, Moerke and Weigert (RFS 2023, "Option return predictability with machine
learning and big data"). The difference: event straddles across earnings, a mispricing target
rather than returns, and a cost-net, matched-null trading test.

Honest limitation, stated in advance: the 2022-2024 megacap years and the 2025-2026 broad block have
been viewed for other selectors in this programme, so neither is untouched by the researcher, only
by this model. The only fully untouched test is forward; a pass here earns a forward test, not a
claim.

## Data

- Block M: `outputs/research/reverse_alpha/panel.parquet` (1,794 megacap events, 2013-2024), outcome
  `return_on_margin` (net, quote marks, frozen cost).
- Block B: `outputs/research/oos_2026_attrition_audit/events.csv` joined to
  `outputs/research/events_broad_oos_2025.parquet` (attrition-corrected 2025-2026 broad block),
  outcome `net_rom`.
- Target y = realised_move / implied_move.
- Features, all known at the entry close: front_atm_iv, back_atm_iv, iv_term_spread, implied_move,
  trailing_rv, skew_25d, vol_premium, variance_risk_premium, bkm_skew, bkm_kurt, t_entry; derived
  log(implied_move), implied_move / (trailing_rv * sqrt(1/252)); the date shift of
  `research_date_shift.py` (missing allowed); and the name's mean y over its prior events in the
  same block (at least 2 prior events, strictly earlier entry dates; missing otherwise).

## Protocol

1. Train on Block M entries in 2013-2018; evaluate candidates on 2019-2021 by Spearman correlation
   between prediction and y. Candidates, fixed now: ridge regression on standardised features with
   median imputation (alpha in {1, 10, 100}); `HistGradientBoostingRegressor` (loss squared error,
   max_depth in {2, 3}, learning_rate 0.05, max_iter in {100, 300}, l2_regularization 1.0,
   min_samples_leaf 40, random_state 0). Nine candidates; the best validation Spearman wins.
2. Refit the winner on 2013-2021. The sell threshold is the 20th percentile of its in-sample
   predictions on 2013-2021 (sell when the predicted ratio is at or below it). Freeze model, feature
   list and threshold; hash the fitted model file.
3. Test once on Block M 2022-2024, then once on Block B, each with the frozen model.

## Decision rule (both the test and the confirmation must pass)

For each of the two evaluation sets:
1. Spearman(prediction, y) > 0 with a date-clustered 95% bootstrap interval above zero.
2. The selected events' mean net RoM exceeds the 95th percentile of 1,000 random selections of the
   same number of events from the same set (seed 0).
3. The selected events' mean net RoM is above zero.
Per-trade Sharpe and DSR against 1,520 trials (the nine candidates count as trials) are reported.

## What is not allowed

No change to features, candidates, split, threshold or tests after any evaluation-set outcome is
seen. The validation years may be inspected freely; the test and confirmation sets are opened once.
