# Freeze: N05 VXTLT event surplus, held-out read

Frozen 2026-11-13 before any held-out (2021-01-01 to 2026-11-12) event-versus-control outcome was
computed. Hypothesis, definitions and the discovery path are in `diagnosis.log` entries 1 to 3.

Held-out tests, read once by `scripts/score_heldout.py`:

- 2212 (co-primary): FOMC statement days, one-day return of a short 30-day ATM TLT straddle marked
  from VXTLT, event minus same-weekday controls. Pass: mean above zero and the 97.5%
  month-clustered lower bound above zero.
- 2213 (co-primary): NFP, CPI and FOMC pooled, same metric and rule.
- 2214, 2215 (secondary, no rule): the H1 variance metric, pooled and FOMC.

Both co-primaries passing is not required for a finding; each stands on its own Bonferroni level.
Every number is gross and index-level: no result here is a tradeable level.

SHA-256 of the inputs and code at freeze:

- scripts/vx_lib.py: 030df0c162c7737259fe7cc3559aaca8720dcabd8b727ee2a2c3a039d07b1095
- scripts/score_heldout.py: b016a10994c66c58233274ac7933b256ca0170b3acf56f3c8fe99e9e66ba213c
- raw/cboe/VXTLT_History.csv: 6d68f6f3671fe4da5b283abae24b09f684354b766de05930aa7ba5a2e355c608
- raw/yahoo/chart_TLT.json: 02e6db30c99e6f7359a499773e30d4640be0d500bb3df62bfe755088abae9796
- data/cache/index_events/macro_releases_2016_2026.csv: 78f52e297f34c3e52ebe9a70e53d33849fa875830eaf430802bdd43ca3b9082a
- this note, all lines above this one: 76b6687643e084262fe162c065cdae13e87fb704e28f8e0eeb7ecd81876d8a88
