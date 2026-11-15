# Freeze note: lane D1, surface network

Written 2026-11-15T16:32:11+00:00 after the development search (40 configurations in `search_log.csv`) and before any 2019-24 outcome was read by this lane.

## Hypothesis, scope and success criteria

Hypothesis: the 15:59 option surface carries information about the distribution of the hedged short-straddle outcome `H_net` beyond L4's features. Scope: D0's targets, 9,315 events with `H_net`; 2019-24 read once per configuration with quarterly refits, then 2025-26 exploratory. Criteria as `diagnosis.log` entry 1 and the brief: forecaster pass (gain against L4 above zero at the date-clustered lower bound, positive in 4 of 6 years); economic pass on `H_net` and `residual_value` against the tight-spread-per-date screen, the pool and the matched random null.

## Frozen configurations

- primary (r2_02): `{"variant": "b", "arch": "conv", "head": "gmm", "K": 1, "width": 32, "depth": 1, "conv_ch": 8, "dropout": 0.1, "weight_decay": 0.001, "lr": 0.001, "use_surface": true}`
  development: `{"n_train_2016": "1037", "n_val_2016": "408", "n_scored_2016": "381", "ls_2016": -3.73747, "gain_l4_2016": 0.01542, "gain_base_2016": 0.02527, "n_params": "3492", "n_train_2017": "1414", "n_val_2017": "376", "n_scored_2017": "529", "ls_2017": -3.62086, "gain_l4_2017": 0.02067, "gain_base_2017": 0.04031, "n_train_2018": "1944", "n_val_2018": "525", "n_scored_2018": "487", "ls_2018": -3.68145, "gain_l4_2018": 0.04654, "gain_base_2018": 0.06421, "n_scored": "1397", "n_no_l4_score": "0", "ls_pooled": -3.67379, "gain_l4_pooled": 0.02825, "gain_base_pooled": 0.04454}`
- secondary (r2_07): `{"variant": "a", "arch": "conv", "head": "gmm", "K": 1, "width": 32, "depth": 1, "conv_ch": 8, "dropout": 0.1, "weight_decay": 0.001, "lr": 0.001, "use_surface": true}`
  development: `{"n_train_2016": "1037", "n_val_2016": "408", "n_scored_2016": "381", "ls_2016": -3.72842, "gain_l4_2016": 0.02447, "gain_base_2016": 0.03432, "n_params": "3492", "n_train_2017": "1414", "n_val_2017": "376", "n_scored_2017": "529", "ls_2017": -3.59988, "gain_l4_2017": 0.04165, "gain_base_2017": 0.06129, "n_train_2018": "1944", "n_val_2018": "525", "n_scored_2018": "487", "ls_2018": -3.68397, "gain_l4_2018": 0.04401, "gain_base_2018": 0.06168, "n_scored": "1397", "n_no_l4_score": "0", "ls_pooled": -3.66425, "gain_l4_pooled": 0.03779, "gain_base_pooled": 0.05407}`
- control_primary (r2_00): `{"variant": "b", "arch": "conv", "head": "gmm", "K": 1, "width": 32, "depth": 1, "conv_ch": 16, "dropout": 0.1, "weight_decay": 0.001, "lr": 0.001, "use_surface": false}`
  development: `{"n_train_2016": "1037", "n_val_2016": "408", "n_scored_2016": "381", "ls_2016": -3.73795, "gain_l4_2016": 0.01494, "gain_base_2016": 0.02479, "n_params": "548", "n_train_2017": "1414", "n_val_2017": "376", "n_scored_2017": "529", "ls_2017": -3.6171, "gain_l4_2017": 0.02444, "gain_base_2017": 0.04408, "n_train_2018": "1944", "n_val_2018": "525", "n_scored_2018": "487", "ls_2018": -3.68035, "gain_l4_2018": 0.04764, "gain_base_2018": 0.06531, "n_scored": "1397", "n_no_l4_score": "0", "ls_pooled": -3.6721, "gain_l4_pooled": 0.02993, "gain_base_pooled": 0.04622}`
- control_secondary (r2_01): `{"variant": "a", "arch": "conv", "head": "gmm", "K": 1, "width": 32, "depth": 1, "conv_ch": 16, "dropout": 0.1, "weight_decay": 0.001, "lr": 0.001, "use_surface": false}`
  development: `{"n_train_2016": "1037", "n_val_2016": "408", "n_scored_2016": "381", "ls_2016": -3.70884, "gain_l4_2016": 0.04405, "gain_base_2016": 0.0539, "n_params": "548", "n_train_2017": "1414", "n_val_2017": "376", "n_scored_2017": "529", "ls_2017": -3.60498, "gain_l4_2017": 0.03655, "gain_base_2017": 0.0562, "n_train_2018": "1944", "n_val_2018": "525", "n_scored_2018": "487", "ls_2018": -3.68708, "gain_l4_2018": 0.0409, "gain_base_2018": 0.05858, "n_scored": "1397", "n_no_l4_score": "0", "ls_pooled": -3.66193, "gain_l4_pooled": 0.04011, "gain_base_pooled": 0.0564}`

Seeds [0, 1, 2, 3, 4], density-averaged. Surfaces sha256 `e7ace0fc0c1e7cb00d2b5c344435e0fa0f11a914576b2ab28aeab1aa9474948f`.
The development gains are the best of the search and so biased upwards; the held-out read is the unbiased one.

## Hashes

scorer_sha256: 49ba5a6a382f943a29c507f62a57d03d0a334ce26817ad1d401bd50db8e8dc37
d1lib_sha256: ff31013e0e425821282983e287a40c36cea08719d72fa7ff81e6569c80596886
d1data_sha256: bea50c50357b1b690ef84151a83ecba1ff11a3fa3267e5b67f641bd848c829d3
d1eval_sha256: 3e62bc67f7cb497234aafc93cf423c8406a68dc4d4cee1e19304f32866e7dc2e
frozen_config_sha256: bf4f7dce68778adf301e8ed6d8f16643843e5032ae198d468a56bcfb31eeb43f
search_log_sha256: 6512075c1953fc4649496a3d111d1d293416a13f66ff28cdae2c2d6e6445850a
self_sha256: c417353f5d5f13abd44d2cbb63a917182592b8941292b52bbc5c1f82c56d4c49
