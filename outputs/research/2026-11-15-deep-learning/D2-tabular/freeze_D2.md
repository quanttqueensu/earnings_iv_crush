# D2 freeze

Written before any 2019-24 or 2025-26 outcome or L4 score was read by this lane.

## Frozen configuration

- Primary (drives the economic rule): c17 `gm1_8_strong`,
  Gaussian head K=1, hidden [8], weight decay
  0.01, dropout 0.2, learning rate
  0.001.
- Secondary (log score only, infinite mean in H_net): c14
  `t_16_strong`, Student-t head, hidden [16].
- Ensemble seeds [0, 1, 2, 3, 4]; averaged mixture densities.
- Rule: trade if the quadrature predictive mean of H_net (% of m0) > 0 (primary head only).
- Refit: each quarter start Q: train on expiry < Q; early stop on entries in [Q - 1 year, Q); refit on the full window for the selected epochs; same seed.
- Selection: best pooled 2016-18 2-seed ensemble log score among eligible GM configurations (c01-c12, c17-c21); best T (c13-c16) for the log-score-only secondary.

## Development scores (2016-18 rolling origin, 2-seed ensemble, real data)

Primary, gain over the L4 champion in nats per event, log density of H_net in % of m0:
2016 +0.0492 (N=381), 2017 +0.0454 (N=529), 2018 +0.0446 (N=487); pooled +0.0462 (N=1397); over the L4
baseline +0.0624. Secondary pooled +0.0376.
Search: 24 configurations of a budget of 24 (search_log.csv), reproduced exactly by a
full re-run with the frozen code (search_log_verify.csv).

## Hashes

score_heldout.py refuses to run unless every file under sha256 hashes as recorded and this note
hashes to its self-hash.

```json
{
 "sha256": {
  "score_heldout.py": "c59452a9ba16fc8daa3e644074ac2d91db40f0557be8c3f6f8d8a8b3208383fa",
  "d2lib.py": "f89b7c051201f37fc695bfe5fd1bd14c047bdfe59a89987c07c114764daf754a",
  "d2net.py": "4c6f2936dc114985b291603716be404098b32a826802675f5ccf258fc1951955",
  "frozen_config.json": "9ab43bda4a3b012b8b9f2a176b4bbebd2b2c19bc9e3be272fc441a7777717d6e",
  "search_log.csv": "5ab68d4d39dc707f04fb6587ae0ca65249e1f15bc187e108f44572b8bae327e9"
 },
 "context_sha256": {
  "stage2_configs.json": "4a794e8e08fa384f9d602e1df26167dabc9501606487f9180498e6347faa07f3",
  "search_log_raw_appended.csv": "348042895763b871f3ac5cbdac03c51d884b2da61f1b195306f3642888364c5b",
  "search_log_verify.csv": "cfae1dd318c31a9d6f5ee26174a65b8df08da6dfa2eecec037fd3008f28a710a",
  "dev_economics.json": "deb7ef64be7ae1d083e1ad38a57521d8031ed0f3965df99d9596ed3cfb0636f8",
  "search.py": "072c1c640c706b67842d11eb68522896d7820b6d01342f49d68e2b42c7d1bee3",
  "../../../../tests/research/test_dl_tabular.py": "56ebca2b11226cc9e6ca42e7a4ad1860786ca48e1ba7b96e27bb47653639cf37"
 },
 "written_utc": "2026-11-15T16:30:52+00:00"
}
```

freeze_self_sha256: 3e5d0bbd321bdaecde6221b4a133fef2367f658654b308e97fe94483df3a1c10
