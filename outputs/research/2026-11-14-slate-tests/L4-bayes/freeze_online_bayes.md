# Freeze note: L4 sequential Bayesian model, iteration round 1

Written 2026-11-15T07:32:11+00:00 after the discovery search and before any held-out outcome of this round was computed.

## Hypothesis, scope and success criteria

Hypothesis: a sequential conjugate model of the per-trade hedged-hold outcome on 15:59 features forecasts its distribution better than the same model with only an intercept and a name effect. Scope: the base panel's 9,350 events, outcomes from `L1-corrections/base_corrected.parquet`, per trade, net at the touch, % of m0. Primary pass (declared in `diagnosis.log` entry 1): the mean per-event log-score difference, model minus baseline, above zero with the date-clustered 95% lower bound above zero, on 2019-24 and on 2025-26 separately. Kill: the 2019-24 point estimate at or below zero. Both held-out blocks were viewed for this outcome family before this lane, so every held-out number is exploratory. Book rules (entry 4): P(H_corr > 0) > 0.5 and the predictive mean above zero, each against a date-stratified random null (pass at the 95th percentile) and with its mean's interval for the economic read.

## Champions (selected by discovery log score alone)

### H_corr

Search rows for this target in `search_log.csv`: 568 (model and baseline classes together).

- Model: `{"discount": 1.0, "variance_discount": 0.99, "coef_prior_scale": 0.03, "name_prior_scale": 0.01, "variance_weight": "none", "obs_df": 30.0, "group_prior_scale": 0.0, "variance_power": 2.0, "feature_set": "declared", "z_clip": Infinity, "target_transform": "yj_loss", "yj_power": 0.0, "group_level": "none", "score": -3.6993240573729365}`
- Baseline: `{"discount": 1.0, "variance_discount": 0.99, "coef_prior_scale": 0.01, "name_prior_scale": 0.03, "variance_weight": "none", "obs_df": 30.0, "group_prior_scale": 0.0, "variance_power": 2.0, "feature_set": "declared", "z_clip": Infinity, "target_transform": "yj_loss", "yj_power": 0.0, "group_level": "none", "score": -3.7136216617324287}`
- Discovery (trial 3012, fit block, in sample for the search): mean log-score difference +0.01430 nats per event, date-clustered 95% [+0.00707, +0.02176], N 1806, 489 dates; median +0.01276; by year {"2015": 0.01389, "2016": 0.00781, "2017": 0.01745, "2018": 0.01628}.
- Calibration on discovery, model: 90% coverage 0.899, PIT below 0.05 0.054, above 0.95 0.047; baseline 0.898, 0.048, 0.055.
- Power: minimum detectable difference on 2019-24 (N 5113, 80% power, 5% two-sided, design effect 1.04) 0.00649 nats per event. The discovery difference is the best of the search, so it is biased upwards; the held-out read is the unbiased one.

### residual_value

Search rows for this target in `search_log.csv`: 232 (model and baseline classes together).

- Model: `{"discount": 0.98, "variance_discount": 0.99, "coef_prior_scale": 0.1, "name_prior_scale": 0.03, "variance_weight": "premium_share", "obs_df": 4.0, "group_prior_scale": 0.03, "variance_power": 2.0, "feature_set": "wide", "z_clip": 5.0, "target_transform": "none", "yj_power": 1.0, "group_level": "sic_div", "score": -2.5596176743323493}`
- Baseline: `{"discount": 0.98, "variance_discount": 0.99, "coef_prior_scale": 0.01, "name_prior_scale": 0.1, "variance_weight": "premium_share", "obs_df": 6.0, "group_prior_scale": 0.0, "variance_power": 2.0, "feature_set": "declared", "z_clip": Infinity, "target_transform": "none", "yj_power": 1.0, "group_level": "none", "score": -2.8408486145035146}`
- Discovery (trial 3017, fit block, in sample for the search): mean log-score difference +0.28123 nats per event, date-clustered 95% [+0.25219, +0.31180], N 1806, 489 dates; median +0.33377; by year {"2015": 0.29123, "2016": 0.33141, "2017": 0.25696, "2018": 0.25994}.
- Calibration on discovery, model: 90% coverage 0.912, PIT below 0.05 0.065, above 0.95 0.023; baseline 0.911, 0.084, 0.005.
- Power: minimum detectable difference on 2019-24 (N 5113, 80% power, 5% two-sided, design effect 1.00) 0.02446 nats per event. The discovery difference is the best of the search, so it is biased upwards; the held-out read is the unbiased one.

## Frozen configuration

```json
{
  "H_corr": {
    "model": {
      "discount": 1.0,
      "variance_discount": 0.99,
      "coef_prior_scale": 0.03,
      "name_prior_scale": 0.01,
      "variance_weight": "none",
      "obs_df": 30.0,
      "group_prior_scale": 0.0,
      "variance_power": 2.0,
      "feature_set": "declared",
      "z_clip": Infinity,
      "target_transform": "yj_loss",
      "yj_power": 0.0,
      "group_level": "none",
      "score": -3.6993240573729365
    },
    "baseline": {
      "discount": 1.0,
      "variance_discount": 0.99,
      "coef_prior_scale": 0.01,
      "name_prior_scale": 0.03,
      "variance_weight": "none",
      "obs_df": 30.0,
      "group_prior_scale": 0.0,
      "variance_power": 2.0,
      "feature_set": "declared",
      "z_clip": Infinity,
      "target_transform": "yj_loss",
      "yj_power": 0.0,
      "group_level": "none",
      "score": -3.7136216617324287
    },
    "search_rows": 568
  },
  "residual_value": {
    "model": {
      "discount": 0.98,
      "variance_discount": 0.99,
      "coef_prior_scale": 0.1,
      "name_prior_scale": 0.03,
      "variance_weight": "premium_share",
      "obs_df": 4.0,
      "group_prior_scale": 0.03,
      "variance_power": 2.0,
      "feature_set": "wide",
      "z_clip": 5.0,
      "target_transform": "none",
      "yj_power": 1.0,
      "group_level": "sic_div",
      "score": -2.5596176743323493
    },
    "baseline": {
      "discount": 0.98,
      "variance_discount": 0.99,
      "coef_prior_scale": 0.01,
      "name_prior_scale": 0.1,
      "variance_weight": "premium_share",
      "obs_df": 6.0,
      "group_prior_scale": 0.0,
      "variance_power": 2.0,
      "feature_set": "declared",
      "z_clip": Infinity,
      "target_transform": "none",
      "yj_power": 1.0,
      "group_level": "none",
      "score": -2.8408486145035146
    },
    "search_rows": 232
  }
}
```

## Hashes

scorer_sha256: d8842fbeca18264c3a412a5ab6516864242651453507fbdd7d3a208209673994
module_sha256: 4d4cefb757e8e347e6ea9002add46ce58719526cd5e0c841847a2ed983097a09
l4lib_sha256: 42c3127d89353177d1485355f4a4f7a5b27cff0e78d9c89c385d7af7bb6af934
l4iter_sha256: 6f88c88a350a61e776ed229205cfb1ad4550ee5b5a8b10bc155ba3863fce42e6
base_sha256: 7d8022f84214afa1c05b8a17d9d7f5abf6a208e57044574a2d591b50288fdd93
search_log_sha256: ba51968a3f6b7da34ebb6e5cd3d799fc0f7139a332385e8d874f8fb6463a6aed
self_sha256: 18cba3ad9c9f22ceac21acd9211e0176a194a557c349f5c04a89800478ed56dc
