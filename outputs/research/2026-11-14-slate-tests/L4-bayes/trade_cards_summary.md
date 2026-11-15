# Trade cards: the twenty largest surprises

Source: `trade_cards.parquet` (every number below is computed from it by `trade_cards.py`). Surprise is the normalised quantile residual of the realised H_corr under the frozen champion's prior predictive (standard normal if the forecast is right; negative is worse for the seller than forecast). Basis: per trade, % of m0, net at the touch. Pool: 8834 scored events, 2013-26; the 2019-24 and 2025-26 parts are walk-forward and exploratory (both blocks were viewed before this lane).

## The twenty

| Rank | Block | Surprise | PIT | H_corr | Premium | Settlement | Hedge | Other | Pred. median | P(H>0) | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2019-24 | -4.69 | 1.34e-06 | -22.8 | +0.9 | -23.4 | +0.0 | -0.34 | -0.2 | 0.36 | skip |
| 2 | 2013-18 | -4.34 | 7.00e-06 | -75.3 | +4.9 | -33.5 | -46.5 | -0.26 | -0.3 | 0.46 | skip |
| 3 | 2019-24 | -4.21 | 1.28e-05 | -37.6 | +2.1 | -19.1 | -20.8 | +0.27 | -0.9 | 0.24 | skip |
| 4 | 2019-24 | -3.67 | 1.23e-04 | -101.6 | +15.7 | -88.3 | -17.3 | -11.74 | +0.4 | 0.52 | trade |
| 5 | 2019-24 | -3.60 | 1.62e-04 | -90.6 | +14.8 | -70.6 | -16.5 | -18.39 | +0.6 | 0.53 | trade |
| 6 | 2019-24 | -3.42 | 3.17e-04 | -78.8 | +15.4 | -84.8 | +0.7 | -10.07 | +0.9 | 0.55 | trade |
| 7 | 2019-24 | -3.33 | 4.28e-04 | -92.3 | +19.6 | -102.9 | -9.0 | -0.06 | +3.7 | 0.65 | trade |
| 8 | 2019-24 | -3.33 | 4.32e-04 | -37.3 | +5.3 | -47.3 | +4.8 | -0.06 | -1.2 | 0.34 | skip |
| 9 | 2025-26 | -3.32 | 4.43e-04 | -76.9 | +16.5 | -93.3 | +0.0 | -0.17 | +2.4 | 0.62 | trade |
| 10 | 2013-18 | -3.31 | 4.73e-04 | -60.8 | +10.2 | -70.6 | +0.0 | -0.37 | -0.3 | 0.48 | skip |
| 11 | 2013-18 | -3.28 | 5.14e-04 | -64.7 | +12.5 | -32.0 | -45.0 | -0.20 | +0.8 | 0.55 | trade |
| 12 | 2019-24 | -3.15 | 8.15e-04 | -37.7 | +5.4 | -43.4 | +0.7 | -0.39 | -1.5 | 0.32 | skip |
| 13 | 2019-24 | -3.14 | 8.41e-04 | -83.3 | +19.4 | -100.9 | -1.6 | -0.11 | +2.8 | 0.61 | trade |
| 14 | 2019-24 | -3.13 | 8.60e-04 | -86.3 | +20.0 | -117.2 | +11.0 | -0.21 | +2.5 | 0.60 | trade |
| 15 | 2013-18 | -3.09 | 1.01e-03 | -71.5 | +16.7 | -73.9 | -14.2 | -0.10 | +1.0 | 0.55 | trade |
| 16 | 2019-24 | -3.05 | 1.14e-03 | -42.8 | +15.1 | -57.6 | +0.0 | -0.37 | +4.0 | 0.72 | trade |
| 17 | 2013-18 | -3.03 | 1.21e-03 | -45.4 | +11.6 | -56.7 | +0.0 | -0.26 | +1.6 | 0.61 | trade |
| 18 | 2019-24 | -3.00 | 1.36e-03 | -44.3 | +13.2 | -57.2 | +0.0 | -0.32 | +1.7 | 0.61 | trade |
| 19 | 2019-24 | -2.98 | 1.46e-03 | -99.5 | +27.9 | -144.9 | +17.6 | -0.08 | +3.2 | 0.59 | trade |
| 20 | 2013-18 | -2.97 | 1.47e-03 | -33.0 | +8.1 | -42.7 | +1.8 | -0.15 | +0.6 | 0.56 | trade |

## What they had in common

- Direction: 20 of 20 are losses beyond the forecast (negative surprise), 0 are gains beyond it.
- Blocks: {'2019-24': 13, '2013-18': 6, '2025-26': 1} against the pool's {'2019-24': 0.579, '2013-18': 0.244, '2025-26': 0.177} (shares).
- Distinct announcement dates 20, distinct names 18.
- Mean components, top 20 against the pool (% of m0): premium +12.77 vs +20.40; settlement -68.02 vs -21.02; hedge -6.72 vs -0.04; equity_cost -2.04 vs -0.13; fees -0.06 vs -0.08; disposal -0.06 vs -0.02; financing -0.00 vs -0.06.
- Settlement share of the miss: the settlement component explains 74% of the top 20's excess loss over the pool mean.
- Flags: ex-dividend in hold 0.05 (N 20) vs 0.10 (N 8662); call assigned 0.00 (N 20) vs 0.04 (N 8834).
- Features at entry (mean causal z of the top twenty is not stored; raw means, top vs pool): log_half_spread -2.534 vs -3.065; log_implied_move -3.342 vs -2.945; iv_term_spread +0.381 vs +0.308; iv_term_spread_missing +0.050 vs +0.092; log_depth +4.963 vs +4.894; log1p_dte +0.761 vs +1.664; log_forward +4.791 vs +4.549; premium_pct_m0 +12.768 vs +20.400.
- Robust weight when absorbed (lambda_hat, 1 is full weight): median 0.717 against the pool's 1.018.
- Largest single-trade shift of any coefficient's posterior mean among the twenty: 0.0039 (model scale), against the pool's 99th percentile 0.0027.
