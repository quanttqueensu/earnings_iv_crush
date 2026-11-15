# Amendment 03 to the SPY macro straddle pre-registration

Applies to `research/off_earnings/preregs/spy_macro_straddle_prereg.md` (SHA-256 97169169...),
families A1 and A2 only (the vega run-up test is closed and unaffected). Written before any return,
P&L or price change was computed from the new source, and frozen with the study
`research/off_earnings/2026-11-01-index-event-crush/` (record
`outputs/research/prereg_2026-11-01-index-event-crush.json`, which also hashes this file).

## What changed and why

The original test was data-infeasible on DoltHub (findings `research/off_earnings/findings/spy_macro.md`):
the source samples about three sessions a week and rotates expiries, so the one-session hold could
not be built. The Databento OPRA `cbbo-1m` history pulled for the index event study carries every
listed SPY contract at 15:59 ET on every session, so the hold can be built as originally written.

## Changes

1. **Source.** SPY quotes come from `data/cache/index_chains/SPY_{date}_1559.parquet` (OPRA
   `cbbo-1m`, the minute beginning 15:59:00 ET, last record per contract), not DoltHub.
2. **Amendments 01 and 02 are withdrawn for this execution.** They adapted the rules to DoltHub's
   sampling. The hold is one session (entry at the 15:59 snapshot of the session before D, exit at
   D's), and the expiry is the shortest listed expiry strictly after D, as in the original text.
   The expiry must have at least one strike with both legs two-sided at entry; the strike rule is
   unchanged (minimise |call mid - put mid|).
3. **Exit at the touch needs only the ask.** The original drops a trade whose exit leg lacks a
   two-sided quote. The short touch arm (A1) needs the exit ask and the long touch arm (A2) the exit
   bid; a trade is kept for an arm when the quote that arm trades on is positive, and the mid arms
   keep the two-sided rule. Drops are counted per arm.
4. **Window and calendar unchanged.** 2019-01-02 to 2024-12-31 and `data/cache/spy_macro/releases.csv`
   (SHA-256 f0c36526...), exactly as frozen.
5. **Commissions.** None in the original. Reported both ways; the decision uses the original basis
   (touch, no commission) so the rule is executed as frozen. A pass that disappears with USD 0.65
   per contract per side is reported as such.

Everything else (families, 97.5% Bonferroni intervals, matched controls within 3 days of tenor and
60 trading days, the five-control minimum, the mechanism check) is unchanged.

## Confirmation, declared here

If a family passes on 2019-2024, it is confirmed on the 2016-2018 and 2025-2026 blocks pooled, using
`data/cache/index_events/macro_releases_2016_2026.csv` for those years and the same rules. The family
is reported as confirmed only if the paired interval on the pooled confirmation blocks excludes zero
in the family's direction.
