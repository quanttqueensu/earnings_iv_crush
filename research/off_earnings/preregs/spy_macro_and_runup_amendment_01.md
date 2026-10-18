# Amendment 01 to the SPY macro straddle and vega run-up pre-registrations

Applies to `_private/spy_macro_straddle_prereg.md` (SHA-256 97169169...) and
`_private/vega_runup_prereg.md` (SHA-256 1fce8039...). Written after the coverage of the source was
inspected and before any return, P&L or price change was computed for either test.

## What was found

The DoltHub `dolthub/options` source does not carry a snapshot every trading day. For SPY in 2019 it
carries almost none; from 2020 it carries Mondays, Wednesdays and Fridays. Single names follow the
same pattern (AAPL, 2020-01-21 to 2020-01-24: snapshots on the 22nd and 24th only). A snapshot is
also stamped on at least one exchange holiday (2020-01-20), with an expiry set unlike the adjacent
sessions. The one-session holds both pre-registrations assume therefore cannot be built for most
events.

## Changes

1. **Usable snapshots.** Only snapshots dated on NYSE sessions (`engine.stats.nyse_sessions`, plus
   the 2025-01-09 closure not relevant here) are used. Holiday-stamped snapshots are discarded.
2. **SPY macro test.** Entry is the latest usable snapshot strictly before release day D and no more
   than 3 sessions before it; exit is D's snapshot, which must exist. The hold length h (1, 2 or 3
   sessions) is recorded. Control trades are every pair of consecutive usable snapshots, at most 3
   sessions apart, whose exit day carries no release; the matched control for an event additionally
   requires the same h. Everything else, including the two families, the 97.5% intervals and the
   decision rule, is unchanged.
3. **Vega run-up test.** Exit is the latest usable snapshot on or before the event's `entry_date` and
   no more than 2 sessions before it (otherwise the event is dropped). Entry is the latest usable
   snapshot at least 3 and at most 6 sessions before the exit snapshot. The null window uses the
   same rule around pseudo D-1. The D-3 secondary variant becomes "entry 1 to 2 sessions before the
   exit snapshot". Everything else is unchanged.
4. **Disclosure for earlier work.** The same coverage pattern means earlier DoltHub-based tests whose
   adapter stepped back up to five calendar days (`lookback_days=5`) may have used an entry or exit
   snapshot one or two sessions stale. This is recorded in the findings of this test; it does not
   change those tests' verdicts, which were failures.
