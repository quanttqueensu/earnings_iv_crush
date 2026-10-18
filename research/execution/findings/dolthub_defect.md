# DoltHub option chains: stale exit snapshots invalidate the 2019-2024 DoltHub straddle results

## What the source is

The free DoltHub `dolthub/options` `option_chain` table is a sampled implied-volatility surface, not
a contract history:

- snapshots exist on roughly three sessions a week from 2020 (Mondays, Wednesdays, Fridays for SPY
  and for single names checked), almost none for SPY in 2019, and at least one exchange holiday
  (2020-01-20) carries a snapshot;
- each snapshot lists about three expiries, at roughly 14 and 28 days after the snapshot date plus
  one monthly, and the short expiries rotate from snapshot to snapshot;
- each expiry carries about 20 strikes on a grid that moves with the snapshot (SPY 2022-03-14:
  375, 384, 392, 400; 2022-03-16: 370, 382, 392, 400).

## The defect

`earnings_iv_crush.data.dolthub_options.fetch_option_chain` defaults to `lookback_days=5`: when the
requested date has no snapshot it silently steps back to the latest earlier one. For an event whose
exit session has no snapshot, the "exit" chain is the entry chain.

In `outputs/research/dolthub_sp500_events.parquet` (1,421 events, 2019-2024) and its chain cache
`data/cache/dolthub_spread/`:

| Check | Count |
|---|---|
| Events | 1,421 |
| Entry and exit chain files byte-identical | 769 (54.1%) |
| Event rows with exit IV equal to entry IV | 467 |

## Consequence

Any DoltHub-based quantity that uses an exit-side option price or IV is unreliable for about half
of the events. In particular, the DoltHub replication of the entry-spread filter
(`outputs/research/entry_spread_dolthub/`) priced exits from these chains; its verdict should be
read as **invalid (data defect)**, not as a failure to replicate. It does not change any decision:
the filter came from exploration after a failed test and was never adopted. The
`dolthub_sp500_persistence.csv` output and any term-slope work on the same pipeline carry the same
caveat until rebuilt.

## How to use the source safely

Call `fetch_option_chain(..., lookback_days=0)`, keep only snapshots dated on NYSE sessions
(`engine.stats.nyse_sessions`), and price a round trip only on an expiry and strike present in both
the entry and the exit snapshot, counting the losses in the funnel. Under those rules single names
price acceptably through the shared monthly expiry (922 of 1,212 event windows that have both
snapshots, about three in four, in the vega run-up pull); SPY round trips mostly cannot be priced
(`outputs/research/spy_macro/findings.md`). The adapter default should change to `lookback_days=0`
with an explicit opt-in for stepping back; that is a code change left for review.
