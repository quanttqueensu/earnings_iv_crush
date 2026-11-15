# L3 state

Updated 2026-11-15 03:23 EST. Hard stop 06:30 EST.

Done:
- lane set-up: lib.py, diagnosis.log section 0.
- C1: trial 2,952 fails discovery (c1_results_2013-18.json); cost read c1_cost.json. evidence.md C1.
- C3: underpowered, not run (c3_mde.json). evidence.md C3.
- C8: trial 2,953 passes discovery, fails held-out (c8_results_2013-18.json, c8_results_2019-24.json,
  freeze_c8.md); carried by residual tenor. HELD-OUT ALREADY READ: never re-run --block 2019-24.
- F3: risk read (f3_risk.json, f3_weighted.json). evidence.md F3.
- C2: blocked (sources.csv, diagnosis.log section 5, evidence.md C2).

- E5: trial 2,954 (FES) fails discovery, trial 2,955 (FNQ) underpowered (e5_results_disc.json,
  e5_score_disc.log, e5_data/ from e5_fetch.py). Held-out 2026-04 to 2026-10 NOT read. evidence.md E5.

- Review corrections applied (diagnosis.log section 8): F3 restated against exposure-matched
  baselines (f3_matched.py), C1 sign and payer confound (c1_describe.py), C8 tenor share, funnels
  and stale-spot note (c8_describe.py), freeze_c8_addendum1.md, nine formatted scripts re-run and
  byte-identical.

In progress: none (final message sent).
Not started: none.
Trial numbers used: 2,952, 2,953, 2,954 (2,955 named for FNQ but never scored, so unused).
