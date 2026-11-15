# Freeze: pilot B held-out read, the Deribit monthly-expiry Friday

Written 2026-11-13 after discovery trials 2,352 to 2,358 (diagnosis.log) and before any
held-out outcome is computed. The held-out windows are on disk (pulled for entry data); no
held-out pair, return or settlement has been scored or printed.

## Frozen configuration (trial 2,353 on discovery)

BTC, Deribit. Entry Thursday 09:00 UTC; short ATM straddle on the Friday 08:00 UTC expiry,
strike nearest the index among strikes with both legs traded in the prior four hours; each leg
at its last mark less the median seller's discount to mark on that expiry; taker fee 0.03% of
the index per leg capped at 12.5% of the leg; settlement fee 0.015% on the in-the-money leg
capped at 12.5%; settled at the btc_usd delivery price. Event: last Friday of each month,
2023-01 to 2026-10. Controls: the Fridays one, two and three weeks earlier. Pair value: event
net return on premium minus the mean of the controls' net returns on premium.

## Pass rule and the reads

- 2,366 primary: mean pair value, 95% interval from `date_clustered_ci` (each event date a
  cluster). Pass for the short if the lower bound exceeds zero; for the long if the upper bound
  is below zero; otherwise fail.
- Reported in the same run, not separate trials: normalised move (event minus control, in
  straddle-implied sd), the event leg's own net return on premium (harvestability: a primary
  pass without an event leg interval above zero is a relative premium, not a tradeable one),
  implied and realised variance differences, funnel and drops.
- 2,367 robustness: 2,366 with every pair dropped whose event or control window contains a CPI,
  payrolls or FOMC release (data/cache/deribit/releases.csv).
- 2,368 and 2,369: the normalised-move contrast on the CME and IBIT clocks (ibclock.py),
  informational only; the IB route is already closed by 2,357 and 2,358.

Kill criterion: a 2,366 failure closes the monthly-expiry premium on Deribit. Even a pass does
not make an IB candidate, because the effect does not reach the CME or IBIT clocks on
discovery.

Power and inflation. Discovery gave +0.439 [+0.063, +0.805] at N=36 after four configurations,
so the point estimate is inflated by selection. The held-out block has about 46 events, an
interval half-width near 0.33 if dispersion is unchanged; a true effect of half the discovery
estimate would pass less than half the time. A fail is therefore weak evidence of absence.
Confound stated before the read: the last Friday sits near calendar month-end.

## Files frozen (SHA-256)

| file | sha256 |
|---|---|
| `n10lib.py` | 9b1ccb9023070d9f0e335c7e8511a918c6c7d42ce3b40e4bda6274a9729ab29e |
| `score_pilot_b.py` | eeec395fcc22979f72485508f9bdf01bf1dc3062ce71d7084c256cd7129aede5 |
| `ibclock.py` | 9d317566a3f687f492d12931c9609a89c608006cc122aca81469aa9a797f4379 |
| `pull_deribit.py` | 5918e0344eec172d025c2885fc8849c00600a23d1c6ec5651ff2ac797c70726c |
| `run_heldout.py` | dac6afb8f5e2a8e5a391fd1aad732e9c55a395c92732816a529b35fd0f7bc4aa |

The held-out read runs only through `run_heldout.py`, which re-hashes this note and the files
above, refuses if any differs or post-dates this note, and refuses a second run.

Note SHA-256 (every line above this one): 6d59e348e723b8eab110ab6312ddf33491f0df6f4040146800db4ee7050d20da
